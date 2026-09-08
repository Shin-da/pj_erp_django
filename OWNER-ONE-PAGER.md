# Perfect Jewel — where the systems stand

**As of 9 September 2026.** Written for the owner, not for developers.
Technical detail lives in `PROJECT_WORKLOG.md` (this system) and
`PROJECT-LOG.md` in the `perfect-jewelry-inventory` repo (the old one).

---

## There are two systems, and only one of them runs the shop

**iadmin** — https://perfect-jewel.svojas.co/iadmin/ — is the real one. Staff tag
stock, invoice resellers, take payments and print labels here every day. It is
hosted by an outside developer, on hosting Perfect Jewel does not control.

**The new system** — https://pjsystems.itsshin.dev/ — is a rebuild. It reads a
copy of iadmin's data every day and shows it back. **Nothing typed into it
reaches iadmin.** Treat it as a very good mirror, not a second till.

Cut-over is a decision nobody has made yet. Until it is made, iadmin is the
book of record and the new system is a preview.

---

## What the shop can act on today

| Question | Answer, and where it comes from |
|---|---|
| How many pieces do we have? | **7,964 tagged pieces.** Both systems agree. |
| Where is the stock? | The **By location** list — Main Vault ~5,600, Pullout ~1,170, Admin Room ~400, Show Room ~200, plus a few hundred at reseller rooms. |
| What sold? | iadmin's sold count (577 pieces at last check). |
| Who owes us? | iadmin's payment screens. Money collected in September agrees exactly across both systems (₱3,128,876), so payments are copying reliably. |
| What's the next tag number? | The new system's **Tag sequences** panel — next PJ and next PJGOLD. |

---

## Three numbers that mislead, and what they really mean

**"Assigned: 0" does not mean nothing is out.** Perfect Jewel moves stock to a
reseller by *transferring it to their room*, not by using the assign feature. So
the assign counter sits at zero while hundreds of pieces are off site. The
honest answer to "what's still in the vault" is the location list, never this
tile. The new system now says so on the page; iadmin still does not.

**"Active transfers: 291" on iadmin is not 291 loads in transit.** The old
system was never finished — it can send stock to another location but has no
button to bring it back, so every transfer ever made still counts as open. The
stock arrived long ago. The new system now imports these as completed history.

**The peso figure next to a stock count is a list price, not money.** Roughly
₱202M against company stock is what the tags add up to at asking price. It is
not cash, not cost, and not what the stock would fetch. Money that actually
changed hands is only in the Sales row.

---

## Fixed today

The new system had been quietly drifting. It synced daily, but once a piece was
copied across, its status and location were never updated again — so it showed
337 sold when iadmin showed 577, and parked 6,646 pieces at Head Office that
were really spread across the vault, pullout and showroom. New pieces arrived;
nothing that changed about existing pieces did.

That is now corrected: a sync refreshes stock status, per-piece location and
invoice status, and also brings across the transfer and scan history it was
skipping entirely. The dashboard also now states when it last synced, so a stale
page is visible instead of assumed.

**These numbers will only line up after the next sync runs.**

---

## Still missing in the new system

- No screens for taking payments or making transfers (the records import, but there is nothing to work in).
- No handheld scanner intake — scanners still post to iadmin only.
- No HR, attendance or reporting.
- Everyone who logs in can invoice, return and print. There are no permission levels yet.

## Still risky in iadmin

- The database password sits in plain text in a settings file on the server, and error pages show internal detail to anyone who triggers one.
- Employee records — including passwords, bank details and salaries — are readable in the database as plain text.
- The Tiara/Irys catalogue sync must stay **off**. It replaces the remote catalogue rather than adding to it, and is suspected of sending only 14 products.

---

## Needs a decision from Perfect Jewel

1. **When does the new system become the one staff type into?** Everything else waits on this.
2. **Who is allowed to do what?** Permission levels can't be built until someone says who invoices and who only looks.
3. **Getting off the current hosting.** iadmin runs on a server the business does not control and has no agreement over.

Meanwhile the shared demo login (`1001`) should be retired before the new system
is shown around — it is a known password.
