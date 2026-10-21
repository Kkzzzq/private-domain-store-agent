# AI-Powered Private-Domain E-Commerce Platform

A merchant dashboard and buyer storefront backed by shared product, inventory, and order data, with store-scoped AI assistants for shopping and operations.

The [native setup without virtualization](docs/native-live.md) has passed seven strict acceptance test groups covering MySQL, Redis, Zhipu chat and Embedding-3, and Chroma. The local demo runs at `127.0.0.1:8000`. The original Ollama and Docker options remain available; refer to that guide for the validated native configuration. Cloud-hosted models are identified separately from Ollama.

Requirements and pass criteria for live integration are documented in the [live acceptance PRD](docs/prd-live-acceptance.md), with setup instructions in the [live integration guide](docs/live-acceptance.md). The independent MySQL/Redis/Ollama setup distinguishes implemented functionality, mocked tests, and real-model acceptance. Reports are written to `backend/data/acceptance/`.

## AI Assistants for Buyers and Merchants

See the [assistant PRD](docs/prd.md) for requirements and acceptance criteria. The floating assistant in the merchant dashboard can query the current store's products, orders, business overview, and low-stock alerts. The buyer assistant supports product search and recommendations, the buyer's own orders, and store policies. Both support multi-turn conversations, new conversations, product cards, and explicit fallback notices.

Query tools are read-only. Merchants can generate product proposals, preview and confirm them, and save them as new drafts without overwriting existing products. Buyer recommendation cards support variant selection, adding to cart, and checkout. See the [agent actions PRD](docs/prd-agent-actions.md) for the full flow. Identity and store scope are resolved on the server. The default rate limit is 30 requests per user per minute, and tool calls are recorded in the redacted `agent_tool_logs` audit table. Recommendations support best sellers, browsing preferences, similar products, and budget constraints. Redis stores separate conversation contexts and rate-limit counters. Real-model integration uses LangChain/Ollama function calling; the knowledge base uses heading-based chunking and Chroma. When the model is unavailable, rule-based queries are used and clearly labeled in the interface.

The [requirement-driven recommendation PRD](docs/prd-recommendation-agent.md) describes how the model first retrieves the store's product overview, extracts budget, quantity, category, inclusion, and exclusion constraints, and selects specific in-stock SKUs with explanations. Budget checks use quantity-adjusted subtotals and exclude shipping. Constraints are not silently relaxed when no products match. Zhipu cloud models are also supported; see the [live integration guide](docs/live-acceptance.md) for operation and acceptance boundaries.

Buyer queries include product discovery, SKU availability, budget-based recommendations, personal orders, shipping status, and return policies for custom products. Merchant queries include business summaries, inventory alerts, store orders, and product searches. See [acceptance and troubleshooting](docs/troubleshooting.md) for model and infrastructure validation boundaries and Wireshark troubleshooting steps.

The merchant dashboard and buyer storefront use the same stores, products, and orders. Buyers access a particular store through its share link.

## User Interface

Product photos from Unsplash are stored in `web/covers`, so the local demo does not require external image requests. Selected button highlights, expanding underlines, and card-border hover effects are adapted from [Hover.css](https://github.com/IanLunn/Hover) under the MIT license; the full library is not included.

The top navigation contains the store name, cart, order center, and browsing history.

![Buyer storefront home](docs/screenshots/buyer-home.png)

The homepage is organized into a hero carousel, merchant recommendations, best sellers, custom sections, all products, customer reviews, and after-sales assurances.

**Hero carousel:** A landscape image spans the same width as the product rows. Merchants choose its height, which defaults to 640px, with 22px of space above it. The main image occupies the middle 93.4%; narrow side strips use a blurred copy of the same image with `blur(34px)` and a 90-degree mask fading at 5% and 95%. Clicking the image opens the linked product. Vertically centered arrows use 38px circular buttons, 27px symbols, and a 7%-opacity background. Navigation indicators and automatic advancement are also supported.

The top bar can use a light tint derived from the store theme or a plain white background. The tint fades below the theme-colored border on the page background layer, keeping the border and adjacent cart, order, and history content visible.

![Second hero slide](docs/screenshots/buyer-hero-2.png)

**Product sections:** Each row displays three products with 397px images. A "View all" link opens the section's collection page. Vertically centered arrows advance one item at a time and fade at either end. Recommendations and best sellers each support up to six products.

**Product cards:** Cards display an image, a merchant-defined badge in the top-left corner, and a small cart button in the bottom-left corner. The name and price, including the comparison price, appear in a top hover overlay that avoids the badge. Badge colors use a light background with matching text. Container queries scale badges and cart buttons to the card width.

**All products:** The initial view shows two rows, or eight products. "Show more" adds one row at a time. Once all products are visible, "Collapse" restores the initial two rows.

**Customer reviews:** Two rows of short reviews move in opposite directions and pause on hover. **After-sales assurances** appear at the bottom of the page, with copy configured by the merchant.

Every product card opens the product detail page in the same store. Navigation resets scrolling to the top; filtering within the current page does not.

### Collection Pages

Each homepage section's "View all" link opens a collection page with category filters and sorting on the left, and a search box and product grid on the right. Collections show the full section rather than the homepage's six-product limit.

![Collection page](docs/screenshots/buyer-collection.png)

Merchants define and reorder category labels in the dashboard. Renaming a category also updates the products assigned to it.

Selecting a category immediately updates the product list and count.

![Filtered collection](docs/screenshots/buyer-collection-filtered.png)

The "All products" link opens the store-wide collection. Searches submitted beside the homepage's "All products" heading also open this page.

![Store-wide collection](docs/screenshots/buyer-collection-all.png)

### Product Cards and Quick Buy

The homepage, collections, and browsing history share the same card design. Names and prices remain in the hover overlay, leaving the default view focused on imagery. The cart button opens a quick-buy dialog on the current page, where buyers can select an SPU/SKU and add it to the cart or place an order without leaving the homepage.

![Quick-buy dialog](docs/screenshots/buyer-quickbuy.png)

Badges use merchant-configured colors with a 9%-intensity background and matching text. A product can have up to four tags; the first is shown on its card. Products without tags fall back to a discount or best-seller badge. On 397px cards, badges use 12px text and cart buttons are 40px; on the 294px cards in the four-column grid, these scale to 11.5px and 35px.

### Cross-Store Browsing History

Browsing history combines products viewed across stores in a single Redis-backed list rather than a database table. Cards match the homepage design, with the store name added to the hover overlay. Each card links to the product's own store.

![Browsing history](docs/screenshots/buyer-history.png)

Only the last seven days are retained. Viewing a product again moves it to the front, and the list can be cleared with one action.

**Unlisted and banned products remain in history.** They are hidden from storefront listings and detail pages, but history cards remain visible in a disabled style with "Unlisted" or "Banned" labels. Prices remain visible; opening details and adding to cart are disabled.

### Product Details

The detail page has three columns: vertical thumbnails, a large image, and product information. The 400px information column contains prices, the comparison price and discount, variants, quantity, and two primary actions. Details, specifications, and reviews appear in tabs below. On narrower windows, the information column shrinks to 340px and then 300px to preserve image space.

![Product details](docs/screenshots/buyer-detail.png)

**Images and variants stay synchronized.** Merchants upload a separate image for each variant, and each thumbnail is labeled with its variant name. Selecting a thumbnail, using the main-image arrows, or selecting a variant updates the image, selected variant, price, and stock together. Products with only one image hide the arrows.

![Variant selection](docs/screenshots/buyer-detail-sku.png)

A sticky purchase bar slides into view at the top after the primary action buttons scroll out of view. It follows the current variant and price. Recommendations also appear below the detail page.

![Sticky purchase bar](docs/screenshots/buyer-detail-buybar.png)

### Cart and Orders

The cart supports select-all and bulk deletion, with shipping calculated in the checkout bar. Checkout places shipping information on the left and the order summary on the right.

![Shopping cart](docs/screenshots/buyer-cart.png)

![Checkout](docs/screenshots/buyer-checkout.png)

Unpaid orders display a countdown. A scheduled task cancels orders that remain unpaid for more than 30 minutes and restores their inventory. Order cards have a lightly tinted, theme-bordered header, a white item area with alternating item backgrounds, and a gray action area.

![Buyer orders](docs/screenshots/buyer-orders.png)

### Merchant Dashboard

The dashboard uses a dark top bar and left navigation. Its overview includes four key metrics, recent orders, product sales rankings, and low-stock alerts.

![Business overview](docs/screenshots/admin-dashboard.png)

**Homepage customization** has four tabs for managing storefront content.

Merchants can upload carousel images or supply existing paths, set titles and subtitles, link to products or sections, and reorder slides.

![Carousel management](docs/screenshots/admin-banners.png)

Product sections can be created, renamed, reordered, and configured for manual selection or automatic selection of the six best sellers. Manual selections are limited to six products.

![Section management](docs/screenshots/admin-sections.png)

**Categories** have a dedicated page for creation, renaming, reordering, and deletion. Renaming updates assigned products. Duplicate names and deletion of nonempty categories are rejected.

![Category management](docs/screenshots/admin-categories.png)

**Product tags** control the badges on buyer-facing cards. Merchants can edit names and colors with a live preview. Renaming preserves associations because links store tag IDs; deleting a tag removes its product associations.

![Product tag management](docs/screenshots/admin-tags.png)

**Homepage appearance** controls hero height, the tinted top-bar background, and after-sales assurance copy.

![Homepage appearance settings](docs/screenshots/admin-appearance.png)

The product table includes thumbnails, stock, and low-stock warnings, with inline listing and banning actions. Orders support status filtering and bulk shipping.

The **Variants and Inventory** area in the product editor provides editable variant names, comparison prices, selling prices, stock, and individual images. The frontend rejects comparison prices below the selling price, zero prices, and empty variant names with merchant-facing validation messages.

![Variant and inventory editor](docs/screenshots/admin-product-editor.png)

Destructive actions require confirmation, including deletion of slides, sections, reviews, categories, and tags. Canceling leaves data unchanged. Sections, reviews, categories, and tags support reordering; the complete sequence is written back as `1..n` to avoid duplicate positions.

## Data Model and Consistency

```text
Merchant user  1 -- 1 Store (share code)
Store          1 -- n Categories / Product tags
Store          1 -- n Products (SPUs)
Product        1 -- n SKUs
Product        n -- n Product tags (product_tag_links)
Buyer user     1 -- n Orders
Order          n -- 1 Store
Order          1 -- n Order items
Order item     n -- 1 Product / SKU, with name, variant, and unit-price snapshots
```

Products and tags have a many-to-many relationship. The link table stores tag IDs, so name changes automatically appear on associated products. Categories use names stored on products, so renaming a category also updates those product records.

The buyer storefront has no separate product copy. Listings, checkout, and assistants read the shared `products` and `skus` tables, with status determining visibility and purchase eligibility.

| Status | Merchant dashboard | Buyer storefront | Browsing history |
| --- | --- | --- | --- |
| Listed | Can unlist or ban | Visible; purchasable with sufficient stock | Normal display; can add to cart |
| Unlisted | Can list or ban | Hidden; details unavailable | Retained as "Unlisted"; cannot add to cart |
| Banned | Must unban first, returning to unlisted | Hidden; details unavailable | Retained as "Banned"; cannot add to cart |
| Store closed | Can reopen | Announcement visible; product list empty | Retained as "Store closed"; cannot add to cart |

Browsing history stores product IDs and timestamps per user in Redis with a seven-day expiry. Rendering retrieves current names, prices, and statuses from the product tables, allowing unavailable products to remain in history with the correct label.

Orders belong to both the buyer and the store and can be fulfilled from the merchant dashboard. Later changes to product names or prices do not change existing order snapshots.

## Run Locally

From the parent workspace:

```powershell
cd Project\private-domain-store-agent\backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The storefront supports product and category search, category filtering, sales and price sorting, variants, a cart, shipping addresses, free shipping on orders of CNY 99 or more, and unpaid, awaiting-shipment, and awaiting-receipt order states. The dashboard manages the same products and orders.

Demo accounts:

- Merchant: `merchant` / `merchant123`; dashboard at `/b.html`.
- Buyer: `alice` / `alice123`; store link at `/c.html?code=nanzhi`.
- Second buyer: `bob` / `bob123`; useful for checking that buyers cannot access each other's orders.

Without MySQL and Redis, the application uses SQLite and in-process conversation storage. To run the MySQL + Redis configuration, execute `docker compose up --build` from the repository root.

Redis supports product-list caching, conversation context, browsing history, and frequently accessed checkout data.

The store assistant defaults to local Ollama with `qwen2.5:7b`. If the model is unavailable, product, stock, order, and after-sales queries fall back to rule-based retrieval while retaining the current store scope.

```powershell
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

After signing in as a merchant, call `POST /api/v1/b/knowledge/reindex` to index the rules in `backend/knowledge` into Chroma. If the embedding model is unavailable, after-sales answers use keyword retrieval over the source text.

APScheduler checks for expired unpaid orders every 60 seconds, canceling those older than 30 minutes and restoring stock. Failure to start the scheduler does not prevent the API from running.

## Feature Summary

### Buyer Storefront

- Direct navigation to the cart, orders, and browsing history, with a theme-derived top-bar background.
- Hero carousel with blurred image edges, product links, and merchant-controlled height.
- Recommendations, best sellers, and custom sections with three-card rows and dedicated collection pages.
- Image-first cards with hover details, responsive merchant badges, and in-place variant selection and quick buy.
- Collection filtering, sorting, and search across the full section or store.
- Synchronized variant images, thumbnails, prices, and inventory, plus a sticky purchase bar.
- Shipping addresses, free shipping from CNY 99, unpaid-order countdowns, payment, cancellation, and receipt confirmation.
- Seven-day cross-store browsing history, product reviews, and multi-turn store-assistant conversations.
- Merchant-managed customer reviews and after-sales copy, expandable product listings, and scroll reset on navigation.

### Merchant Dashboard

- Business overview, sales rankings, recent orders, and inventory alerts.
- Product listing, unlisting, banning, and unbanning.
- SKU pricing, comparison prices, inventory, variant images, and per-buyer purchase limits.
- Order filtering, individual shipping, and bulk shipping.
- Store logo, theme color, categories, and product tags.
- Homepage carousel uploads, section management, customer reviews, hero height, top-bar appearance, and after-sales copy.

Storefront content is merchant-configurable within the predefined page structure.

## References and Attribution

The implementation draws on patterns from these projects:

- [imShire/xu-shop](https://github.com/imShire/xu-shop): single-merchant private-domain commerce workflows, atomic stock deduction, low-stock alerts, bulk shipping, and purchase limits.
- [mosliu/ldc-shop](https://github.com/mosliu/ldc-shop): product variants, ratings and reviews, announcements, store themes, and unpaid-order cancellation.
- [Web Awesome](https://webawesome.com/), the successor to [Shoelace](https://github.com/shoelace-style/shoelace): rating and overlay components loaded directly from a CDN without a build step.
- [Hover.css](https://github.com/IanLunn/Hover): button and link hover effects adapted into `web/mall.css`.
- [BpsEason/VueFastMart](https://github.com/BpsEason/VueFastMart): FastAPI + Vue 3 storefront architecture and API layering.

Product photos are provided by [Unsplash](https://unsplash.com/license) under the Unsplash License and stored locally in `web/covers`. File mappings are defined in `COVERS` in `backend/app/seed.py`. The variant images `pillow-blue.jpg`, `runner-blue.jpg`, and `mug-detail.jpg` were generated locally from source images using GDI+ cropping and color adjustments to demonstrate variant-linked imagery.

## Tests

From the parent workspace:

```powershell
cd Project\private-domain-store-agent\backend
.\.venv\Scripts\pytest
```

Coverage includes merchant/buyer data consistency, listing and banning, cross-store isolation, order transitions, purchase limits, overselling prevention, timeout cancellation, bulk shipping, browsing history, reviews, categories, product tags, variant images, and homepage appearance.

## Project Structure

```text
backend/app/api/b_api.py           Merchant dashboard API
backend/app/api/c_api.py           Buyer storefront API
backend/app/services/home.py       Carousel, sections, reviews, and collections
backend/app/services/categories.py Merchant-defined categories
backend/app/services/tags.py       Merchant-defined product badges
backend/app/services/shelf.py      Listing, banning, and purchase eligibility
backend/app/services/trade.py      Cart, shipping addresses, and checkout
backend/app/services/engagement.py Browsing history
backend/app/services/reviews.py    Product reviews
backend/app/services/orders.py     Ordering, payment, shipping, and expiry
backend/app/models/tables.py       Store, product, SKU, cart, address, review,
                                  order, carousel, and section models
backend/app/agent/                 Store-scoped assistants
web/mall.css                      Shared storefront and dashboard styles
web/c.js                          Buyer storefront
web/b.js                          Merchant dashboard
web/covers/                       Demo product images
docs/screenshots/                 Interface screenshots
```
