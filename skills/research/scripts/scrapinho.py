"""Bounded Scrapinho REST client. Provider credentials never belong here."""
import json
import random
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

TERMINAL = {"succeeded", "partial", "blocked", "captcha", "forbidden", "timeout", "parse_error", "cancelled", "failed", "execution_unknown"}


class ScrapinhoError(Exception):
    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, base_url, api_key, timeout=20):
        url = urlsplit(base_url)
        local = url.hostname in {"127.0.0.1", "localhost", "::1"}
        if url.scheme != "https" and not (local and url.scheme == "http"):
            raise ValueError("https_required")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("invalid_service_url")
        if not api_key or timeout <= 0:
            raise ValueError("invalid_client_configuration")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.opener = build_opener(_NoRedirect)

    def _request(self, path, method="GET", payload=None, request_id=None, raw=False, timeout=None):
        headers = {"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json",
                   "User-Agent": "scrapinho-python/0.1"}
        if request_id:
            headers["Idempotency-Key"] = request_id
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=min(self.timeout, timeout or self.timeout)) as response:
                body = response.read(64 * 1024 * 1024 + 1)
                if len(body) > 64 * 1024 * 1024:
                    raise ScrapinhoError("response_too_large")
                if raw:
                    return body
                return json.loads(body) if body else None
        except HTTPError as error:
            body = error.read(65536)
            error.close()
            try:
                code = json.loads(body)["errors"][0]["code"]
            except (ValueError, KeyError, IndexError, TypeError):
                code = "service_http_error"
            raise ScrapinhoError(code, error.code) from None
        except (OSError, ValueError):
            raise ScrapinhoError("service_unavailable") from None

    def capabilities(self):
        return self._request("/v1/capabilities")

    def usage(self, project_scope=None):
        query = urlencode({} if project_scope is None else {"project_scope": project_scope})
        return self._request("/v1/usage?" + query)

    def submit(self, request, request_id=None, timeout=None):
        return self._request("/v1/jobs", "POST", request, request_id or str(uuid4()), timeout=timeout)

    def get(self, job_id, timeout=None):
        return self._request("/v1/jobs/" + job_id, timeout=timeout)

    def get_many(self, job_ids):
        if not 1 <= len(job_ids) <= 50:
            raise ValueError("invalid_job_count")
        return self._request("/v1/jobs?" + urlencode({"ids": ",".join(job_ids)}))["jobs"]

    def map(self, requests, timeout=120):
        """Acquire sequentially; never retry admission or continue after a refusal."""
        results, stopped = [], False
        for request in requests:
            if stopped:
                results.append({"status": "failed", "errors": [{"code": "batch_stopped"}]})
                continue
            job = {}
            deadline = time.monotonic() + timeout
            try:
                job = self.submit(request, timeout=timeout)
                if job.get("status") not in TERMINAL:
                    job = self.wait(job["job_id"], timeout=max(0.001, deadline - time.monotonic()))
                stopped = job.get("status") in {"blocked", "captcha", "forbidden", "execution_unknown"}
            except ScrapinhoError as error:
                stopped = True
                failure = {"code": error.code}
                job = {**job, "status": "failed", "errors": [failure]}
                if job.get("job_id"):
                    try:
                        cancellation = self.cancel(job["job_id"])
                    except ScrapinhoError:
                        job["cancellation_unconfirmed"] = True
                    else:
                        original_errors = job["errors"]
                        job = {**job, **cancellation}
                        job["errors"] = original_errors
                        if cancellation.get("status") == "execution_unknown":
                            job["cancellation_unconfirmed"] = True
                        elif cancellation.get("status") == "cancelled":
                            job["cancellation_unconfirmed"] = False
                results.append(job)
                continue
            results.append(job)
        return results

    def delete_scope(self, project_scope=None):
        query = "" if project_scope is None else "?" + urlencode({"project_scope": project_scope})
        return self._request("/v1/sources" + query, "DELETE")

    def deletion_status(self, project_scope=None):
        query = "" if project_scope is None else "?" + urlencode({"project_scope": project_scope})
        return self._request("/v1/source-deletion" + query)

    def cancel(self, job_id):
        return self._request("/v1/jobs/" + job_id, "DELETE")

    def wait(self, job_id, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get(job_id, timeout=max(0.001, deadline - time.monotonic()))
            if job.get("status") in TERMINAL:
                return job
            delay = min(job.get("next_poll_after_ms", 1000) / 1000, max(0, deadline - time.monotonic()))
            time.sleep(delay * random.uniform(0.8, 1))
        raise ScrapinhoError("client_deadline_exceeded")


    def read_source(self, source_id, view="full", cursor=None, limit=16384, timeout=None):
        params = {"view": view, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._request("/v1/sources/" + source_id + "?" + urlencode(params), timeout=timeout)

    def read_search(self, source_id, timeout=None):
        return self._request("/v1/sources/" + source_id + "/search", timeout=timeout)

    def read_all(self, source_id, view="full", timeout=120):
        text, cursor, digest, fetched_at = [], None, None, None
        deadline = time.monotonic() + timeout
        for _page_number in range(512):
            if time.monotonic() >= deadline:
                raise ScrapinhoError("client_deadline_exceeded")
            page = self.read_source(source_id, view, cursor, timeout=max(0.001, deadline - time.monotonic()))
            if digest is not None and (page["content_sha256"] != digest or page["fetched_at"] != fetched_at):
                raise ScrapinhoError("snapshot_changed")
            digest, fetched_at = page["content_sha256"], page["fetched_at"]
            text.append(page["text"])
            next_cursor = page["next_cursor"]
            if next_cursor is None:
                return {**page, "text": "".join(text)}
            if next_cursor == cursor:
                raise ScrapinhoError("cursor_stalled")
            cursor = next_cursor
        raise ScrapinhoError("source_page_limit")

    def export_source(self, source_id, representation="manifest", timeout=None):
        if representation not in {"manifest", "html", "raw", "decoded_html"}:
            raise ValueError("invalid_representation")
        return self._request("/v1/sources/" + source_id + "/export?" + urlencode({"format": representation}),
                             raw=representation != "manifest", timeout=timeout)

    def delete_source(self, source_id):
        return self._request("/v1/sources/" + source_id, "DELETE")
