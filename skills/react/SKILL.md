---
name: react
description: React/Next.js best practices for modern, performant applications.
---

# React/Next.js Standards

## React 19 Best Practices

- Use Suspense, the `use` hook, and promises as props
- Prefer `use`, `useTransition`, and `startTransition` over `useEffect`
- You probably shouldn't use `useEffect`

## Component Design

- Keep components pure: don't declare constants or functions inside components
- Use React Query for client-side async data fetching
- Don't fetch data in `useEffect`

## Loading & Error States

- Prefer `<Suspense>` and `useSuspenseQuery` over React Query's `isLoading`
- Use `errorBoundary` with retry button

## Cache Management

- Don't use magic strings for cache tags; use an enum/factory
- Use enum for React Query cache strings

## Avoid

- Magic numbers/strings
- Data fetching in useEffect
- Constants inside component bodies
- isLoading patterns when Suspense works
