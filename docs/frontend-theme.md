# NewsPulse frontend theme (default dark)

## What changed

The Next.js app in [`news-pulse-frontend/`](../../news-pulse-frontend/) uses a **single default dark theme** inspired by a compact news-feed mock: near-black background, elevated surfaces, white primary text, gray secondary text, and a blue accent for tabs, links, spinners, and primary actions.

There is **no light/dark toggle** and no change to API routes, data fetching, or navigation behavior—only global CSS tokens and Tailwind class updates on existing components.

## Tokens

Defined in [`news-pulse-frontend/src/app/globals.css`](../../news-pulse-frontend/src/app/globals.css) (`:root` + Tailwind v4 `@theme inline`):

| Token | Role |
|-------|------|
| `background` | App shell (`#121212`) |
| `surface` / `surface-elevated` | Cards, sticky tab bar, chat panel (`#1e1e1e` / `#252525`) |
| `foreground` | Primary text (`#ffffff`) |
| `muted` | Meta, snippets, placeholders (`#a0a0a0`) |
| `border-subtle` | Dividers (low-opacity white) |
| `accent` | Active tab, links, CTAs (`#007aff`) |

Components use Tailwind utilities such as `bg-background`, `bg-surface`, `text-foreground`, `text-muted`, `border-border-subtle`, and `bg-accent` / `text-accent`.

## How to verify

From `news-pulse-frontend/`:

```bash
npm run dev
```

Open the home feed and an article page; confirm readable contrast and sticky tab bar on scroll.

```bash
npm run lint && npm run build
```

## Caveats

- Story thumbnails use `image_url` from the cluster API (`StoryImage` on feed cards and article detail).
- Native form controls inherit `color-scheme: dark` on `body` for basic OS styling consistency.
