# Private Store Agent

**An AI-powered storefront, a merchant workspace, and an agent evaluation platform—in one full-stack project.**

Private Store Agent connects product discovery, shopping, and store operations through a shared commerce backend. Buyers get recommendations grounded in current inventory. Merchants manage their storefront and query business data through conversation. An operations workspace brings assistant evaluation and functional testing into the same project.

Built with **FastAPI · SQLAlchemy · MySQL · Redis · LangChain · Chroma · pytest · Playwright**. Supports local Ollama models and configured cloud providers.

[Quick Start](#quick-start) · [AI Assistants](#ai-assistants) · [Quality Engineering](#quality-engineering) · [Screenshots](#screenshots) · [Documentation](#documentation)

![Buyer storefront](docs/screenshots/buyer-home.png)

## What Makes It Interesting

- **AI connected to actual store data.** Product, stock, order, and policy queries use controlled tools and knowledge retrieval. Recommendations account for budget, quantity, availability, and explicit preferences.
- **A complete shopping workflow.** Browse collections, select variants, add to cart, check out, and track orders, with inventory and order data shared between buyers and merchants.
- **A storefront merchants can shape.** Configure branding, hero slides, product sections, categories, badges, reviews, and after-sales copy from the dashboard.
- **Three distinct agent roles.** Business assistants serve users; an evaluation agent assesses assistant behavior; a functional-testing agent selects registered API and browser checks.
- **Evidence-backed testing.** Approved plans, isolated execution, fixed assertions, tool traces, and browser screenshots support repeatable quality checks.
- **Explicit identity and store boundaries.** Server-resolved identities, store-scoped queries, buyer-specific order access, redacted tool logs, and rate limits make access rules part of the implementation.

## AI Assistants

### For Buyers

Find products, compare available options, ask about stock and policies, and check personal orders. Recommendations select specific in-stock SKUs and explain their fit. Product cards let buyers choose variants and continue to cart or checkout.

The recommendation flow extracts budget, quantity, category, required attributes, and exclusions. Budget checks use quantity-adjusted subtotals before shipping; unmatched constraints are surfaced rather than silently relaxed.

### For Merchants

Ask about store orders, business performance, and low-stock products. Generate product configuration proposals, review them, and save confirmed proposals as new drafts while preserving existing products.

### How They Work

- **Tool calling:** LangChain/Ollama integration and configured cloud-model support connect conversations to business tools.
- **Retrieval:** Heading-based knowledge chunks and Chroma support policy and after-sales answers.
- **Conversation memory:** Redis-backed contexts keep conversations separate across users.
- **Access control:** Identity and store scope are determined on the server; query tools are read-only.
- **Observability:** Redacted calls are recorded in `agent_tool_logs`; the default limit is 30 requests per user per minute.
- **Fallback behavior:** Model outages use explicitly labeled rule-based queries; embedding outages use keyword retrieval over policy sources.

See the [assistant requirements](docs/prd.md), [agent action flows](docs/prd-agent-actions.md), and [recommendation design](docs/prd-recommendation-agent.md).

## Commerce Experience

### Buyer Storefront

An image-led interface combines a hero carousel, curated collections, best sellers, and a searchable catalog. Shared product cards offer hover details and quick buy, while variant-linked imagery keeps the selected image, price, and inventory aligned.

The shopping flow includes shipping addresses, free shipping from CNY 99, order countdowns, cancellation, and receipt confirmation. A sticky purchase bar keeps the selected variant accessible on product pages. Cross-store browsing history retains the last seven days, including clearly labeled unavailable products.

### Merchant Workspace

Manage products, SKU prices and stock, variant images, purchase limits, listings, categories, and tags. Track business metrics, recent orders, sales rankings, and inventory alerts; filter orders and ship individually or in bulk.

Homepage customization covers carousel uploads and ordering, product sections, reviews, theme colors, hero height, and after-sales messaging. Destructive actions require confirmation.

![Merchant business overview](docs/screenshots/admin-dashboard.png)

### Three Layers: SPU, SKU, and a Buyer-Side Wide Table

`products` is the SPU table and the authority: name, category, images, status, sales count, purchase limit, and the customer-facing `spu_id`. `skus` holds per-variant price, stock, image, parameters, and points back to its SPU through `spu_id`. Merchant and operations interfaces read and write these two tables directly, so what they see is always the real value.

Buyer-facing product display (home, collections, detail, category filters, search, browsing history, cart, current order images) come from `c_product_views`, one row per SPU holding the assembled card payload. Draft is a status value on the SPU, not a separate table; drafts are not projected at all, so a buyer-side query cannot leak one even if a filter is forgotten.

```text
products (SPU, authoritative) ──┐
skus (SKU, spu_id → products.id)┴─→ c_product_views (buyer-side wide table) → buyer pages
```

The projection is derived data, refreshed three ways: every catalog write (including category renames and tag edits) refreshes the affected rows, before serving the catalog cache, buyer reads check each SPU's display fields and complete SKU payload (including stock, status, images, and parameters) and rebuild any row whose hash moved, and startup rebuilds the whole table. Content is hashed because timestamps only reach the second on MySQL — an edit landing in the same second as the last refresh would otherwise go unnoticed. Shop suspension stays a read-path check rather than a stored field, so freezing a shop takes effect immediately.

Order items preserve names, variants, and unit prices as snapshots, so later catalog edits do not rewrite purchase history. Checkout validates authoritative SKU prices and stock. Stock reservation, cancellation/expiry restoration, and payment sales updates refresh the projection in the same database transaction. Product catalog writes refresh projections explicitly; source tables are also consulted for projection freshness checks, rather than used to assemble buyer display responses.

Unpaid orders expire after 30 minutes. A scheduled sweep runs every 60 seconds to cancel expired orders and restore stock. Product-tag associations use IDs, while category renames update assigned products.

```text
Merchant / Operations → Store → products (SPU) → skus
                                → Categories and product tags
Buyer → c_product_views (wide table)
      → Orders → Order items → Product / SKU snapshots
      → Cross-store browsing history in Redis
```

## Quality Engineering

The operations workspace separates business assistance, assistant evaluation, and functional testing into distinct roles.

- **Assistant evaluation:** Build plans for registered scenarios, inspect tool traces and retrieved evidence, and assess results against explicit assertions.
- **Functional testing:** Execute registered pytest checks and real-browser scenarios for business state transitions, permissions, and UI behavior.
- **Controlled planning:** Review and approve model-proposed plans before execution. Registered runners constrain what can be executed.
- **Isolated runs:** Test fixtures and subprocesses keep test execution separate from existing store data.
- **Traceable results:** Preserve case versions, run reports, and browser screenshots; compare reports under compatible conditions.

Mocked tests, isolated regression, native dependency checks, and real-model acceptance are tracked separately. Rule-based fallback does not count as successful real-model evaluation.

See the [quality center](docs/quality-center.md), [agent implementation guide](docs/agent-basics.md), and [CI regression workflow](.github/workflows/quality-regression.yml).

## Screenshots

<details>
<summary><strong>Explore the buyer experience</strong></summary>

### Discovery and Collections

![Hero carousel](docs/screenshots/buyer-hero-2.png)
![Collection page](docs/screenshots/buyer-collection.png)
![Category filtering](docs/screenshots/buyer-collection-filtered.png)
![Full product catalog](docs/screenshots/buyer-collection-all.png)

### Product Selection

![Quick buy](docs/screenshots/buyer-quickbuy.png)
![Product details](docs/screenshots/buyer-detail.png)
![Variant-linked imagery](docs/screenshots/buyer-detail-sku.png)
![Sticky purchase bar](docs/screenshots/buyer-detail-buybar.png)

### Shopping and Order Tracking

![Shopping cart](docs/screenshots/buyer-cart.png)
![Checkout](docs/screenshots/buyer-checkout.png)
![Order center](docs/screenshots/buyer-orders.png)
![Cross-store browsing history](docs/screenshots/buyer-history.png)

</details>

<details>
<summary><strong>Explore the merchant workspace</strong></summary>

![Carousel management](docs/screenshots/admin-banners.png)
![Homepage sections](docs/screenshots/admin-sections.png)
![Category management](docs/screenshots/admin-categories.png)
![Product badges](docs/screenshots/admin-tags.png)
![Storefront appearance](docs/screenshots/admin-appearance.png)
![Variants and inventory](docs/screenshots/admin-product-editor.png)

</details>

## Quick Start

### Local Demo

Clone the repository, then create a Python environment and start the backend:

```powershell
git clone https://github.com/Kkzzzq/private-domain-store-agent.git
cd private-domain-store-agent\backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

- **Merchant:** `merchant` / `merchant123` — `/b.html`
- **Buyer:** `alice` / `alice123` — `/c.html?code=nanzhi`
- **Second buyer:** `bob` / `bob123` — available for checking buyer-order isolation.
- **Operations workspace:** `/op.html` — see the [quality center guide](docs/quality-center.md) for access and setup.

The lightweight configuration uses SQLite and in-process conversation storage when MySQL and Redis are not configured. The demo storefront and its existing screenshots use Chinese UI text.

### AI Setup

The default local-model option uses Ollama:

```powershell
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

After merchant login, call `POST /api/v1/b/knowledge/reindex` to index `backend/knowledge` into Chroma. For cloud models and live integration, follow the [configuration and acceptance guide](docs/live-acceptance.md).

### MySQL and Redis

From the repository root:

```powershell
docker compose up --build
```

A [native setup guide](docs/native-live.md) also documents operation without virtualization, including MySQL, Redis, Zhipu chat and Embedding-3, and Chroma.

## Tests and Validation

From `backend`, using the environment created above:

```powershell
.\.venv\Scripts\pytest
```

The test suite covers buyer/merchant data consistency, store isolation, listing restrictions, order transitions, purchase limits, overselling prevention, timeout cancellation, bulk shipping, browsing history, reviews, categories, tags, variant images, and homepage configuration.

Live integration requirements and pass criteria are documented in the [acceptance PRD](docs/prd-live-acceptance.md). Generated acceptance reports are stored in `backend/data/acceptance/`. See [troubleshooting](docs/troubleshooting.md) for model and infrastructure diagnostics.

## Project Structure

```text
backend/app/api/          Buyer, merchant, and operations endpoints
backend/app/services/     Catalog, inventory, checkout, and order logic
backend/app/agent/        Business assistants and controlled tool calls
backend/app/rag/          Knowledge retrieval and routing
backend/app/quality/      Planning, evaluation, runners, and reports
backend/app/models/       Shared commerce and operations data models
backend/knowledge/        Policy and after-sales source documents
backend/tests/            Backend and regression tests
web/                      Buyer, merchant, and operations interfaces
web/covers/               Local demo product photos
docs/                     Requirements, guides, and acceptance records
docs/screenshots/         Interface screenshots
.github/workflows/        CI regression and deployment workflows
```

## Documentation

- [Assistant requirements](docs/prd.md)
- [Agent actions and confirmation flows](docs/prd-agent-actions.md)
- [Constraint-aware recommendations](docs/prd-recommendation-agent.md)
- [Quality center](docs/quality-center.md)
- [Agent implementation guide](docs/agent-basics.md)
- [Live integration and model configuration](docs/live-acceptance.md)
- [Native infrastructure setup](docs/native-live.md)
- [Live acceptance requirements](docs/prd-live-acceptance.md)
- [Troubleshooting and diagnostics](docs/troubleshooting.md)

## References and Attribution

Implementation references include [imShire/xu-shop](https://github.com/imShire/xu-shop) for inventory and fulfillment patterns, [mosliu/ldc-shop](https://github.com/mosliu/ldc-shop) for storefront features, and [BpsEason/VueFastMart](https://github.com/BpsEason/VueFastMart) for API layering.

UI components use [Web Awesome](https://webawesome.com/), the successor to [Shoelace](https://github.com/shoelace-style/shoelace), with selected effects adapted from [Hover.css](https://github.com/IanLunn/Hover) under the MIT license.

Product photos are stored locally in `web/covers` and used under the [Unsplash License](https://unsplash.com/license). Source mappings are defined in `COVERS` in `backend/app/seed.py`. The demo variant images `pillow-blue.jpg`, `runner-blue.jpg`, and `mug-detail.jpg` were derived from source images using local GDI+ cropping and color adjustments.
