# RECON OS — UI/UX DESIGN SPECIFICATION

## 1. PRODUCT DESIGN DIRECTION

RECON OS is not a generic AI dashboard.

It is an autonomous financial operations system.

The interface should feel like a serious fintech infrastructure product used by merchants, finance teams, payment operations teams, and eventually Razorpay operators.

The visual quality should be comparable to modern products such as:

- Razorpay Dashboard
- Stripe Dashboard
- Linear
- Vercel
- modern fintech operations platforms

However:

DO NOT COPY ANY WEBSITE PIXEL-FOR-PIXEL.

Use these products only as inspiration for:

- information hierarchy
- spacing
- typography
- navigation
- data visualization
- interaction patterns
- financial dashboard usability

RECON OS must have its own visual identity.

---

# 2. CORE VISUAL CONCEPT

RECON OS should feel like:

"Mission Control for Revenue Recovery"

The user should immediately understand:

What is happening?
What revenue is at risk?
What is RECON doing?
What requires attention?
What has been recovered?
Why did the system make a decision?

The interface should prioritize operational visibility over decoration.

---

# 3. DESIGN PRINCIPLES

## Principle 1 — Information Density

The interface should present a lot of useful information without feeling cluttered.

Use:

- cards
- tables
- timelines
- charts
- status indicators
- side panels
- command surfaces

Avoid:

- giant empty hero sections
- excessive whitespace
- decorative illustrations
- unnecessary marketing-style sections

This is an OPERATIONS PRODUCT, not a landing page.

---

# 4. VISUAL STYLE

Primary direction:

Premium fintech + developer infrastructure + AI operations.

Use:

- dark primary interface
- near-black background
- subtle surface elevation
- thin borders
- muted secondary text
- bright primary accent
- restrained gradients
- subtle glow only where meaningful
- glass effects sparingly
- smooth micro-interactions

Do NOT use:

- excessive neon
- cyberpunk aesthetics
- excessive glassmorphism
- rainbow gradients
- huge glowing text
- unnecessary 3D objects

The UI should feel sophisticated, not flashy.

---

# 5. COLOR SYSTEM

Use a restrained fintech color system.

Background:

Very dark / near black.

Surface:

Slightly lighter dark panels.

Border:

Subtle neutral borders.

Primary accent:

Razorpay-inspired blue family, but do not simply reproduce Razorpay's exact branding.

Success:

Green.

Warning:

Amber.

Danger:

Red.

Information:

Blue.

All colors must have accessible contrast.

Status colors should communicate meaning consistently.

---

# 6. TYPOGRAPHY

Use a modern sans-serif font.

Recommended:

Inter or Geist.

Typography hierarchy:

Page title
→ Section heading
→ Card heading
→ Body
→ Metadata

Numbers such as:

₹42.8L

₹31.4L

78.7%

should be visually prominent.

Financial values should use tabular/monospaced numerical alignment where appropriate.

---

# 7. GLOBAL APPLICATION SHELL

Use a persistent application shell.

Layout:

┌─────────────────────────────────────────────────────────┐
│ RECON OS                              Search   Profile  │
├──────────────┬──────────────────────────────────────────┤
│              │                                          │
│ Command      │                                          │
│ Center       │                                          │
│              │                                          │
│ Live Events  │              MAIN CONTENT                │
│              │                                          │
│ Recovery     │                                          │
│              │                                          │
│ Customers    │                                          │
│              │                                          │
│ Simulator    │                                          │
│              │                                          │
│ Audit Log    │                                          │
│              │                                          │
│ Settings     │                                          │
│              │                                          │
└──────────────┴──────────────────────────────────────────┘

Sidebar:

- RECON OS logo
- Command Center
- Live Events
- Recovery
- Customers
- Simulator
- Audit Log
- Settings

Later phases can add:

- AI Agents
- Intelligence
- Policies
- Approvals
- Analytics

Do not create empty meaningless pages just for navigation.

---

# 8. COMMAND CENTER

This is the most important page.

It should feel like a financial control room.

Top section:

RECON OS
Revenue Recovery Command Center

Status:

● SYSTEM OPERATIONAL

Then KPI cards:

Revenue at Risk
₹42.8L

Revenue Secured
₹24.7L

Active Recovery Cases
128

Payment Failures
342

Events Processed
18,492

Cards should include:

- value
- label
- comparison/trend if real data exists
- small visualization where useful

Do NOT fabricate trend data.

If there is insufficient historical data, show:

"Awaiting historical data"

rather than fake percentages.

---

# 9. REVENUE VISUALIZATION

Create a high-quality revenue chart.

Possible:

Revenue at Risk vs Revenue Secured

or:

Payment Success / Failure trend.

The chart should:

- have useful hover states
- display exact values
- use subtle grid lines
- have clear labels
- adapt to available data
- never fabricate values

---

# 10. LIVE RECON ACTIVITY

The Command Center should include a real-time activity stream.

Example:

14:32:01
PAYMENT FAILED
₹8,499
Demo Customer

14:32:02
RECOVERY CASE CREATED
Case #RC-10291

14:32:03
EVENT PROCESSED
payment.failed

14:32:05
PAYMENT CAPTURED
₹12,499

Each event should have:

- timestamp
- event type
- amount
- customer
- status
- expandable details

Use subtle motion when new events arrive.

Do not create fake activity.

---

# 11. RECOVERY CASE VISUALIZATION

Recovery cases should feel like operational objects.

Example:

┌──────────────────────────────────────────────────────────┐
│ RECOVERY CASE #RC-10291                                  │
│                                                          │
│ ₹8,499                                                   │
│ Payment failed                                           │
│                                                          │
│ Customer        ABC Corp                                │
│ Payment Method  UPI                                     │
│ Failure         Payment processing failed              │
│ Created         14:32:01                                │
│                                                          │
│ STATUS                                                   │
│ ● OPEN                                                   │
│                                                          │
│ EVENT TIMELINE                                           │
│                                                          │
│ ● Payment failed                                         │
│ │                                                        │
│ ● Case created                                           │
│ │                                                        │
│ ○ Diagnosis                                             │
│ │                                                        │
│ ○ Recovery                                              │
│                                                          │
└──────────────────────────────────────────────────────────┘

Phase 1 should only show states actually implemented.

Do not visually pretend that AI diagnosis or recovery has happened yet.

---

# 12. LIVE EVENTS PAGE

Create an advanced event table.

Columns:

Timestamp
Event
Payment
Customer
Amount
Status

Example:

payment.failed
pay_xxx
ABC Corp
₹8,499
FAILED

Features:

- search
- filtering
- pagination
- event type filter
- status filter
- date filter if practical
- detail drawer

Clicking an event should open a side panel rather than navigating away when possible.

The side panel should show:

- normalized event
- raw event payload
- timestamps
- processing status
- associated payment
- associated customer
- associated recovery case

Raw JSON should be displayed in a readable developer-style viewer.

---

# 13. RECOVERY PAGE

Display:

- Active cases
- Revenue at risk
- Open cases
- Resolved cases
- Cases by failure type

Use a professional data table.

Columns:

Case ID
Customer
Amount
Failure
Status
Created
Priority

Priority in Phase 1 must be deterministic.

Do not use AI risk scoring.

---

# 14. CUSTOMER PAGE

Customer profiles should feel like financial intelligence profiles.

Example:

ABC Corp

Total Payments
₹2.84L

Successful
31

Failed
3

Revenue at Risk
₹8,499

Then:

Payment History

Timeline:

✓ ₹25,000 captured
✓ ₹15,000 captured
✕ ₹8,499 failed
✓ ₹40,000 captured

Phase 1 must use factual database information.

Do not display AI-generated risk scores yet.

---

# 15. SIMULATOR PAGE

This page is critical for the buildathon demo.

Make it feel like a controlled event laboratory.

Title:

RECON EVENT SIMULATOR

Description:

"Generate controlled payment events to test the RECON recovery pipeline."

Scenario cards:

PAYMENT FAILED

PAYMENT CAPTURED

PAYMENT AUTHORIZED

Each scenario should allow:

Customer
Amount
Currency
Payment Method
Failure Reason

Button:

TRIGGER EVENT

After triggering:

Show:

EVENT GENERATED
↓
WEBHOOK PIPELINE
↓
EVENT STORED
↓
PAYMENT UPDATED
↓
RECOVERY CASE CREATED

The simulator must use the real backend pipeline.

Do not create frontend-only fake state.

---

# 16. PHASE-AWARE UI

RECON OS will evolve.

Phase 1:

DATA / CONNECT

Show:

- Events
- Payments
- Customers
- Recovery Cases
- Revenue at Risk
- Revenue Secured
- Simulator
- Audit

Phase 2:

THINK

Add:

- AI Agents
- Diagnosis
- Recovery Probability
- Strategy
- Policy Decision

Phase 3:

ACT

Add:

- Action Execution
- Approvals
- Payment Links
- Outcome Verification

Phase 4:

PROVE

Add:

- Analytics
- Evaluation
- Strategy Performance
- Recovery Metrics

Do not show unfinished functionality as if it exists.

---

# 17. FUTURE AI AGENT UI

When Phase 2 begins, introduce an AI operations visualization.

Example:

RECOVERY CASE

DETECTED
   ↓
DIAGNOSING
   ↓
PREDICTING
   ↓
STRATEGIZING
   ↓
POLICY CHECK
   ↓
EXECUTING
   ↓
VERIFYING
   ↓
RECOVERED

Each step should display:

- status
- timestamp
- agent
- decision
- confidence
- rationale

The AI should be transparent.

Do not simply display:

"AI is thinking..."

Instead show meaningful structured decisions.

---

# 18. COMMAND PALETTE

Implement a command palette if practical.

Shortcut:

CMD/CTRL + K

Possible commands:

Go to Command Center
Go to Events
Go to Recovery
Go to Customers
Open Simulator
Search payment
Search customer
Search recovery case

This should make RECON OS feel like an actual operating system.

---

# 19. GLOBAL SEARCH

Provide search across:

- payment ID
- customer
- event ID
- recovery case ID

Search should query the backend.

Do not build fake frontend-only search.

---

# 20. MICRO-INTERACTIONS

Use subtle animations for:

- page transitions
- card updates
- event arrival
- status changes
- drawers
- modals
- chart interactions

Keep animation fast and professional.

Avoid excessive animation.

---

# 21. RESPONSIVE DESIGN

The application must work on:

- desktop
- laptop
- tablet

Desktop is the primary target.

Do not sacrifice desktop information density to create a mobile-first marketing layout.

---

# 22. ACCESSIBILITY

Implement:

- keyboard navigation
- visible focus states
- semantic HTML
- accessible buttons
- appropriate ARIA labels
- sufficient contrast
- reduced-motion support where practical

---

# 23. EMPTY STATES

Never leave blank screens.

Example:

No recovery cases:

"All clear — no active recovery cases."

No events:

"Waiting for revenue events..."

No customers:

"No customer activity yet."

No historical chart data:

"Historical data will appear as events accumulate."

Empty states should explain what the user should do next.

---

# 24. ERROR STATES

Design professional error states.

Examples:

API unavailable:

"RECON backend unavailable"

with:

Retry

Webhook failure:

"Webhook could not be processed"

with useful technical context.

Never show raw stack traces to users.

---

# 25. LOADING STATES

Use skeleton loaders rather than blank screens.

Tables:

Skeleton rows.

Cards:

Skeleton blocks.

Charts:

Chart skeleton.

---

# 26. DATA INTEGRITY

This is extremely important.

Every displayed metric must originate from the backend/database.

Never hardcode:

- revenue
- payment counts
- recovery counts
- customer data
- event data
- percentages

unless it is clearly labeled demo/sample data.

The simulator should create actual records.

---

# 27. VISUAL HIERARCHY

The most important information should visually dominate:

1. Revenue at Risk
2. Revenue Secured
3. Active Recovery Cases
4. Live Payment Events
5. Recovery Case Details
6. Supporting analytics

Avoid giving equal visual weight to everything.

---

# 28. RAZORPAY-INSPIRED DESIGN LANGUAGE

Use inspiration from Razorpay's product ecosystem:

- clean fintech layout
- strong blue accent
- simple navigation
- professional data presentation
- strong typography
- clear financial metrics
- minimal visual noise

BUT:

Do NOT copy Razorpay logos, exact branding, proprietary illustrations, or exact page layouts.

RECON OS should look like an independent product built for the Razorpay ecosystem.

---

# 29. RECON BRAND IDENTITY

Product name:

RECON OS

Possible tagline:

"Autonomous Revenue Recovery"

Alternative:

"Turn Payment Failures Into Recovery."

Logo direction:

Minimal geometric mark representing:

- detection
- loop
- recovery
- network

Use a simple SVG logo.

Do not create an overly complicated logo.

---

# 30. DESIGN QUALITY BAR

The final interface should feel:

Premium
Professional
Fast
Technical
Trustworthy
Operational
Data-driven
AI-native

It should NOT feel:

Generic
Template-based
Over-designed
Cyberpunk
Gaming-inspired
Like a student CRUD application
Like an AI landing page

---

# 31. IMPLEMENTATION RULE

Before implementing the UI:

Create a visual design plan for:

1. App shell
2. Command Center
3. Events
4. Recovery
5. Customers
6. Simulator

Then implement the system.

Do not create every page as a separate unrelated design.

All pages must share:

- typography
- spacing
- colors
- components
- navigation
- status system
- cards
- tables
- drawers
- buttons

Create reusable design components.

---

# 32. IMPORTANT

RECON OS is an OPERATING SYSTEM / COMMAND CENTER.

Do not build it like a marketing website.

The user should feel:

"I am operating a live revenue recovery system."

Not:

"I am viewing a beautiful AI landing page."
