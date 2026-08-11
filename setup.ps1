# my-llm-kit :: native Windows installer. Idempotent and safe to preview with -DryRun.
[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoDirectory = $PSScriptRoot
$InstallManifestPath = Join-Path $RepoDirectory "install-manifest.json"
$InstallManifest = Get-Content -Raw -Path $InstallManifestPath | ConvertFrom-Json
$ScrapingDogMcpPackage = "https://codeload.github.com/badmuriss/Scrapingdog-mcp/tar.gz/8084d8a77b5836f7c0ef7cfbaec5ab12f1fcb741"
$HomeDirectory = [Environment]::GetFolderPath("UserProfile")
$DocumentsDirectory = [Environment]::GetFolderPath("MyDocuments")
if ([string]::IsNullOrWhiteSpace($DocumentsDirectory)) {
    $DocumentsDirectory = Join-Path $HomeDirectory "Documents"
}
$SkillsRoot = Join-Path $HomeDirectory ".agents\skills"
$HostSkillDirectories = @()
$Results = @()
$HadFailure = $false

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE"
    }
}

function Invoke-Python {
    param([string[]]$Arguments = @())
    if (Test-Command "py") {
        Invoke-Native "py" (@("-3") + $Arguments)
        return
    }
    if (Test-Command "python") {
        Invoke-Native "python" $Arguments
        return
    }
    throw "Python 3 is required. Install it and rerun setup.ps1."
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $Action
        $status = "ok"
    }
    catch {
        $status = "FAILED"
        $script:HadFailure = $true
        Write-Warning "${Name}: $($_.Exception.Message)"
    }
    finally {
        $stopwatch.Stop()
        $script:Results += "{0,-36} {1,-7} {2,4}s" -f $Name, $status, [int]$stopwatch.Elapsed.TotalSeconds
    }
}

function Get-BackupPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $candidate = "$Path.bak-$(Get-Date -Format yyyyMMdd)"
    $suffix = 1
    while (Test-Path -LiteralPath $candidate) {
        $candidate = "$Path.bak-$(Get-Date -Format yyyyMMdd)-$suffix"
        $suffix += 1
    }
    return $candidate
}

function Test-ReparsePoint {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $item = Get-Item -Force -LiteralPath $Path
    return ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
}

function New-DirectoryJunction {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Target
    )
    if (Test-Path -LiteralPath $Path) {
        if (-not (Test-ReparsePoint $Path)) {
            throw "$Path is a real directory; refusing to replace it"
        }
        $existingTarget = [string](Get-Item -Force -LiteralPath $Path).Target
        if (-not [string]::IsNullOrWhiteSpace($existingTarget)) {
            $existingTarget = [IO.Path]::GetFullPath($existingTarget).TrimEnd("\")
            $desiredTarget = [IO.Path]::GetFullPath($Target).TrimEnd("\")
            if ($existingTarget -ieq $desiredTarget) {
                return
            }
        }
        if ($DryRun) {
            Write-Host "  [dry-run] replace junction $Path -> $Target"
            return
        }
        Remove-Item -Force -LiteralPath $Path
    }
    elseif ($DryRun) {
        Write-Host "  [dry-run] junction $Path -> $Target"
        return
    }
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    New-Item -ItemType Junction -Path $Path -Target $Target | Out-Null
}

function Add-HostSkillLink {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Canonical
    )
    foreach ($hostDirectory in $HostSkillDirectories) {
        $target = Join-Path $hostDirectory $Name
        if ((Test-Path -LiteralPath $target) -and -not (Test-ReparsePoint $target)) {
            Write-Host "  $target is a real directory, leaving it alone"
            continue
        }
        New-DirectoryJunction -Path $target -Target $Canonical
    }
}

function Link-Skill {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Source
    )
    $canonical = Join-Path $SkillsRoot $Name
    $sourcePath = [IO.Path]::GetFullPath($Source).TrimEnd("\")
    $canonicalPath = [IO.Path]::GetFullPath($canonical).TrimEnd("\")
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null
    }

    if ($sourcePath -ine $canonicalPath) {
        if ((Test-Path -LiteralPath $canonical) -and -not (Test-ReparsePoint $canonical)) {
            $backupRoot = Join-Path $HomeDirectory ".agents\skills-backup"
            $backup = Get-BackupPath (Join-Path $backupRoot $Name)
            if ($DryRun) {
                Write-Host "  [dry-run] move $canonical to $backup"
            }
            else {
                New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
                Move-Item -LiteralPath $canonical -Destination $backup
                Write-Host "  backup saved at $backup"
            }
        }
        New-DirectoryJunction -Path $canonical -Target $sourcePath
    }
    Add-HostSkillLink -Name $Name -Canonical $canonicalPath
}

function Install-ManagedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )
    if ($DryRun) {
        Write-Host "  [dry-run] copy $Source to $Target"
        return
    }
    $parent = Split-Path -Parent $Target
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $Target) {
        $sameContent = $null -eq (Compare-Object (Get-Content -Raw $Source) (Get-Content -Raw $Target))
        if ($sameContent) {
            return
        }
        $backup = Get-BackupPath $Target
        Copy-Item -LiteralPath $Target -Destination $backup
        Write-Host "  backup saved at $backup"
    }
    Copy-Item -Force -LiteralPath $Source -Destination $Target
}

if ((Test-Command "claude") -or (Test-Path (Join-Path $HomeDirectory ".claude"))) {
    $HostSkillDirectories += (Join-Path $HomeDirectory ".claude\skills")
}
if ((Test-Command "codex") -or (Test-Path (Join-Path $HomeDirectory ".codex"))) {
    $HostSkillDirectories += (Join-Path $HomeDirectory ".codex\skills")
}

Write-Host "my-llm-kit :: Windows setup"
Write-Host "repo:        $RepoDirectory"
Write-Host "skill root:  $SkillsRoot"
if ($HostSkillDirectories.Count -gt 0) {
    Write-Host "fan out to:  $($HostSkillDirectories -join ', ')"
}
else {
    Write-Host "fan out to:  (none detected)"
}
if ($DryRun) {
    Write-Host "dry-run mode: no changes will be made"
}
Write-Host ""

Invoke-Step "check binaries and manifest" {
    $missing = @()
    foreach ($binary in @("git", "node", "npm", "npx")) {
        if (-not (Test-Command $binary)) {
            $missing += $binary
        }
    }
    if (-not (Test-Command "py") -and -not (Test-Command "python")) {
        $missing += "python"
    }
    if ($null -eq $InstallManifest.own_repositories -or $null -eq $InstallManifest.reduced_install_skills) {
        throw "$InstallManifestPath does not match the installer contract"
    }
    if ($missing.Count -gt 0) {
        throw "missing required binaries: $($missing -join ', ')"
    }
    $hosts = @(@("claude", "codex", "opencode", "gemini", "copilot", "cursor-agent") |
        Where-Object { Test-Command $_ })
    if ($hosts.Count -gt 0) {
        Write-Host "  agent hosts found: $($hosts -join ', ')"
    }
    else {
        Write-Host "  no agent host binary found; skills will still install"
    }
}

Invoke-Step "pip markitdown+paper-search" {
    if ($DryRun) {
        Write-Host "  [dry-run] python -m pip install --user markitdown[all] paper-search-mcp 'mcp<2.0.0'"
    }
    else {
        Invoke-Python @("-m", "pip", "install", "--quiet", "--user", "markitdown[all]", "paper-search-mcp", "mcp<2.0.0")
    }
}

Invoke-Step "register MCP paper-search" {
    if (Test-Command "claude") {
        $listing = (& claude mcp list 2>$null | Out-String)
        if ($listing -match "(?m)^paper-search") {
            Write-Host "  claude: paper-search already registered, skipping"
        }
        elseif ($DryRun) {
            Write-Host "  [dry-run] claude mcp add --scope user paper-search -- paper-search-mcp"
        }
        else {
            Invoke-Native "claude" @("mcp", "add", "--scope", "user", "paper-search", "--", "paper-search-mcp")
        }
    }
    if (Test-Command "codex") {
        $listing = (& codex mcp list 2>$null | Out-String)
        if ($listing -match "paper-search") {
            Write-Host "  codex: paper-search already registered, skipping"
        }
        elseif ($DryRun) {
            Write-Host "  [dry-run] codex mcp add paper-search -- paper-search-mcp"
        }
        else {
            Invoke-Native "codex" @("mcp", "add", "paper-search", "--", "paper-search-mcp")
        }
    }
    if (Test-Command "opencode") {
        Write-Host '  opencode: add {"mcp":{"paper-search":{"type":"local","command":["paper-search-mcp"]}}} to opencode.json'
    }
}

Invoke-Step "install MCP scrapingdog" {
    if ($DryRun) {
        Write-Host "  [dry-run] npm install --global $ScrapingDogMcpPackage"
    }
    else {
        Invoke-Native "npm" @("install", "--global", $ScrapingDogMcpPackage)
        $packageDirectory = Join-Path ((& npm root --global | Out-String).Trim()) "scrapingdog-mcp"
        Invoke-Native "npm" @("ci", "--include=dev", "--prefix", $packageDirectory)
    }
}

Invoke-Step "register MCP scrapingdog" {
    $entrypoint = Join-Path ((& npm root --global | Out-String).Trim()) "scrapingdog-mcp\dist\index.js"
    if (Test-Command "claude") {
        $details = (& claude mcp get scrapingdog 2>$null | Out-String)
        if ($details.Contains($entrypoint)) {
            Write-Host "  claude: scrapingdog already points to the pinned build, skipping"
        }
        elseif ($DryRun) {
            if (-not [string]::IsNullOrWhiteSpace($details)) {
                Write-Host "  [dry-run] claude mcp remove scrapingdog -s user"
            }
            Write-Host "  [dry-run] claude mcp add --scope user scrapingdog -- node $entrypoint"
        }
        else {
            if (-not [string]::IsNullOrWhiteSpace($details)) {
                Invoke-Native "claude" @("mcp", "remove", "scrapingdog", "-s", "user")
            }
            Invoke-Native "claude" @("mcp", "add", "--scope", "user", "scrapingdog", "--", "node", $entrypoint)
        }
    }
    if (Test-Command "codex") {
        $details = (& codex mcp get scrapingdog 2>$null | Out-String)
        if ($details.Contains($entrypoint)) {
            Write-Host "  codex: scrapingdog already points to the pinned build, skipping"
        }
        elseif ($DryRun) {
            if (-not [string]::IsNullOrWhiteSpace($details)) {
                Write-Host "  [dry-run] codex mcp remove scrapingdog"
            }
            Write-Host "  [dry-run] codex mcp add scrapingdog -- node $entrypoint"
        }
        else {
            if (-not [string]::IsNullOrWhiteSpace($details)) {
                Invoke-Native "codex" @("mcp", "remove", "scrapingdog")
            }
            Invoke-Native "codex" @("mcp", "add", "scrapingdog", "--", "node", $entrypoint)
        }
    }
    if (Test-Command "opencode") {
        Write-Host "  opencode: add {`"mcp`":{`"scrapingdog`":{`"type`":`"local`",`"command`":[`"node`",`"$entrypoint`"]}}} to opencode.json"
    }
    if ([string]::IsNullOrWhiteSpace($env:SCRAPINGDOG_API_KEY)) {
        Write-Host "  scrapingdog registered without a key; set SCRAPINGDOG_API_KEY before starting an agent"
    }
}

Invoke-Step "preflight MCP scrapingdog" {
    $entrypoint = Join-Path ((& npm root --global | Out-String).Trim()) "scrapingdog-mcp\dist\index.js"
    if ($DryRun) {
        Write-Host "  [dry-run] node scripts/preflight_scrapingdog_mcp.mjs $entrypoint"
    }
    else {
        Invoke-Native "node" @((Join-Path $RepoDirectory "scripts\preflight_scrapingdog_mcp.mjs"), $entrypoint)
    }
}

Invoke-Step "preflight paper-search" {
    if ($DryRun) {
        Write-Host "  [dry-run] paper-search-mcp --version"
        Write-Host "  [dry-run] paper-search search 'CodePlan repository-level coding' -s arxiv -n 1"
        return
    }
    foreach ($executable in @("paper-search-mcp", "paper-search")) {
        if (-not (Test-Command $executable)) {
            Write-Host "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
            throw "$executable is missing after installation"
        }
    }
    Invoke-Native "paper-search-mcp" @("--version")
    $queryOutput = (& paper-search search "CodePlan repository-level coding" -s arxiv -n 1 2>&1 | Out-String)
    $queryExitCode = $LASTEXITCODE
    if ($queryExitCode -ne 0) {
        Write-Host "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
        throw "paper-search query failed with exit code ${queryExitCode}: $($queryOutput.Trim())"
    }
    if ($queryOutput -notmatch "CodePlan|2309\.12499") {
        Write-Host "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
        throw "paper-search query returned no identifiable result: $($queryOutput.Trim())"
    }
    Write-Host "  paper-search query returned CodePlan"
}

Invoke-Step "vendored skills including grill-me" {
    Get-ChildItem -Directory (Join-Path $RepoDirectory "skills") | ForEach-Object {
        Link-Skill -Name $_.Name -Source $_.FullName
    }
}

Invoke-Step "own skill repositories" {
    foreach ($repository in $InstallManifest.own_repositories) {
        $target = Join-Path $DocumentsDirectory $repository.name
        if (-not (Test-Path -LiteralPath $target)) {
            if ($DryRun) {
                Write-Host "  [dry-run] git clone $($repository.url) $target"
            }
            else {
                Invoke-Native "git" @("clone", $repository.url, $target)
            }
        }
        Link-Skill -Name $repository.name -Source $target
    }
}

Invoke-Step "community skills" {
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null
    }
    foreach ($skill in $InstallManifest.community_skills) {
        $target = Join-Path $SkillsRoot $skill.name
        if (-not (Test-Path -LiteralPath $target)) {
            if ($DryRun) {
                Write-Host "  [dry-run] git clone $($skill.url) $target"
            }
            else {
                Invoke-Native "git" @("clone", $skill.url, $target)
            }
        }
        Link-Skill -Name $skill.name -Source $target
    }
}

Invoke-Step "firecrawl CLI and skills" {
    $firecrawlSkill = Join-Path $SkillsRoot "firecrawl"
    if (Test-Path -LiteralPath $firecrawlSkill) {
        Write-Host "  firecrawl skills already present, skipping"
    }
    elseif ($DryRun) {
        Write-Host "  [dry-run] npm install -g firecrawl-cli; firecrawl setup skills"
    }
    else {
        if (-not (Test-Command "firecrawl")) {
            Invoke-Native "npm" @("install", "-g", "firecrawl-cli")
        }
        Invoke-Native "firecrawl" @("setup", "skills")
    }
}

Invoke-Step "fan out every skill" {
    if (-not (Test-Path -LiteralPath $SkillsRoot)) {
        Write-Host "  skill root does not exist yet; earlier dry-run steps show planned links"
        return
    }
    Get-ChildItem -Directory $SkillsRoot | ForEach-Object {
        Add-HostSkillLink -Name $_.Name -Canonical $_.FullName
    }
}

Invoke-Step "AGENTS.md" {
    $source = Join-Path $RepoDirectory "AGENTS.md"
    $shared = Join-Path $HomeDirectory ".agents\AGENTS.md"
    Install-ManagedFile -Source $source -Target $shared
    foreach ($alias in @(
        (Join-Path $HomeDirectory ".claude\CLAUDE.md"),
        (Join-Path $HomeDirectory ".codex\AGENTS.md")
    )) {
        if (Test-Path -LiteralPath (Split-Path -Parent $alias)) {
            Install-ManagedFile -Source $shared -Target $alias
        }
    }
}

function Install-PluginsForHost {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][string]$InstallVerb
    )
    $listing = (& $HostName plugin list 2>$null | Out-String)
    foreach ($entry in $InstallManifest.plugins) {
        $installed = if ($HostName -eq "claude") {
            $listing.Contains($entry.plugin)
        }
        else {
            ($listing -split "`n" | Where-Object { $_.Contains($entry.plugin) -and $_ -match "installed," }).Count -gt 0
        }
        if ($installed) {
            Write-Host "  ${HostName}: $($entry.plugin) already installed, skipping"
            continue
        }
        if ($DryRun) {
            Write-Host "  [dry-run] $HostName plugin marketplace add $($entry.marketplace); $HostName plugin $InstallVerb $($entry.plugin)"
            continue
        }
        $addOutput = (& $HostName plugin marketplace add $entry.marketplace 2>&1 | Out-String)
        $addExitCode = $LASTEXITCODE
        if ($addExitCode -ne 0) {
            if ($addOutput -notmatch "already added from a different source") {
                throw "${HostName}: could not add marketplace $($entry.marketplace): $($addOutput.Trim())"
            }
            $marketplaceName = ($entry.plugin -split "@")[-1]
            Write-Host "  ${HostName}: replacing stale marketplace $marketplaceName"
            Invoke-Native $HostName @("plugin", "marketplace", "remove", $marketplaceName)
            Invoke-Native $HostName @("plugin", "marketplace", "add", $entry.marketplace)
        }
        Invoke-Native $HostName @("plugin", $InstallVerb, $entry.plugin)
    }
}

Invoke-Step "plugins for Claude Code and Codex" {
    $found = $false
    if (Test-Command "claude") {
        Install-PluginsForHost -HostName "claude" -InstallVerb "install"
        $found = $true
    }
    if (Test-Command "codex") {
        Install-PluginsForHost -HostName "codex" -InstallVerb "add"
        $found = $true
    }
    if (-not $found) {
        Write-Host "  neither Claude Code nor Codex is installed, skipping plugins"
    }
}

Invoke-Step "agent resource guard" {
    Write-Host "  agent resource guard is Linux-only; Windows skips it explicitly"
}

$DcgPath = Join-Path $HomeDirectory ".local\bin\dcg.exe"
Invoke-Step "dcg destructive command guard" {
    if (-not (Test-Path -LiteralPath $DcgPath)) {
        if ($DryRun) {
            Write-Host "  [dry-run] run the official native Windows dcg PowerShell installer"
        }
        else {
            $installerUrl = "https://raw.githubusercontent.com/Dicklesworthstone/destructive_command_guard/main/install.ps1"
            $installer = Invoke-RestMethod -Uri $installerUrl
            & ([scriptblock]::Create([string]$installer)) -EasyMode -Verify
        }
    }
    if ($DryRun) {
        Write-Host "  [dry-run] copy calibrated dcg config, install hooks, and run doctor"
        return
    }
    if (-not (Test-Path -LiteralPath $DcgPath)) {
        throw "dcg installer completed without creating $DcgPath"
    }
    $configDirectory = Join-Path $HomeDirectory ".config\dcg"
    New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
    foreach ($name in @("config.toml", "allowlist.toml")) {
        $source = Join-Path (Join-Path $RepoDirectory "dcg") $name
        $target = Join-Path $configDirectory $name
        Install-ManagedFile -Source $source -Target $target
    }
    Invoke-Native $DcgPath @("install")
    & $DcgPath doctor
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "dcg doctor reported issues"
    }
}

$PipelockPath = Join-Path $HomeDirectory ".local\bin\pipelock.exe"
Invoke-Step "pipelock agent traffic guard" {
    $installerArguments = @(
        (Join-Path $RepoDirectory "scripts\install_pipelock.py"),
        "--target",
        $PipelockPath
    )
    if ($DryRun) {
        $installerArguments += "--dry-run"
    }
    Invoke-Python $installerArguments

    if ($DryRun) {
        if ((Test-Command "codex") -or (Test-Path (Join-Path $HomeDirectory ".codex"))) {
            Write-Host "  [dry-run] $PipelockPath codex install --dry-run"
        }
        if ((Test-Command "claude") -or (Test-Path (Join-Path $HomeDirectory ".claude"))) {
            Write-Host "  [dry-run] $PipelockPath claude setup --dry-run"
        }
        return
    }

    if (-not (Test-Path -LiteralPath $PipelockPath)) {
        throw "Pipelock installer did not create $PipelockPath"
    }
    $configured = $false
    if (Test-Command "codex") {
        Invoke-Native $PipelockPath @("codex", "install")
        $configured = $true
    }
    if (Test-Command "claude") {
        Invoke-Native $PipelockPath @("claude", "setup")
        $configured = $true
    }
    if (-not $configured) {
        Write-Host "  Pipelock installed; no Codex or Claude host found to configure"
    }
}

Write-Host ""
Write-Host "heavy dependencies such as MinerU and docling remain opt-in."
Write-Host ""
Write-Host "== summary =="
$Results | ForEach-Object { Write-Host $_ }

if ($HadFailure) {
    exit 1
}
