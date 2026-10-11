---
kind: doc
status: verified
---

# How to add or change price rules

Finance send a new tariff sheet every spring (new prices from 1 April, the
start of the financial year), plus the odd mid-year "summer offer". This is
how it gets into `price_rules`.

There's no back-office screen for bulk changes yet. The single-rule form at
*Back office → Facilities → Space → Prices* is fine for one or two edits;
for the annual uplift we write a SQL script, have it reviewed, and run it
via the deploy pipeline's `sql` step (not by hand on the box — the staff SQL
console was removed in 2.6.0 for good reasons).

## The rules about rules

- **Never UPDATE a live rule's price.** Close it (`valid_to` = last day) and
  insert a new one (`valid_from` = first day). Existing bookings keep the
  price they were quoted anyway (it's stored on the booking) but reports and
  support staff look at rules to explain old prices.
- `pence_per_hour` is **gross** — VAT-inclusive where VAT applies. Finance
  sheets sometimes give net prices for commercial hire. Ask.
- Use **even** hourly rates. A half-hour costs `pence_per_hour / 2`,
  rounded up. £27.50 is fine (1375p per half hour). £27.55 would cost
  £13.78 per half hour and £27.56 for an hour. The form refuses odd rates;
  SQL won't stop you.
- Times are **local wall-clock** (`local_from`, `local_to`). Don't convert
  anything to UTC. "Evenings 17:00-22:00" means 17:00 local in winter and
  in summer.
- `local_to` is exclusive. 17:00-22:00 covers slots starting 17:00 ... 21:30.
- `weekday_mask`: Monday = 1, Tuesday = 2, Wednesday = 4, ... Sunday = 64.
  Weekdays = 31, weekends = 96, every day = 127.
- `space_id` NULL + `space_kind` set = applies to every space of that kind.
  A rule for a specific space always beats a kind-wide one.
- Overlapping rules: highest `priority` wins, then the newest `valid_from`.
  For a temporary offer, add a rule with `priority = 10` and a `valid_to`;
  don't touch the normal ones.
- `hirer_type` must be one of resident, club, charity, community_group,
  school, commercial. Every space needs rules for every hirer type that can
  book it, or those people get "No price for that time".

## Annual uplift, step by step

1. Get the sheet from Finance (Janet Morley's team). Check it has every
   space kind × hirer type × time band. It usually doesn't; ask about gaps
   rather than guessing.
2. Write the script. Template:

   ```sql
   BEGIN;
   -- close current rules the night before the new year
   UPDATE price_rules SET valid_to = DATE '2026-03-31'
    WHERE valid_to IS NULL AND space_kind = 'sports_hall' AND space_id IS NULL;

   INSERT INTO price_rules (space_kind, hirer_type, weekday_mask, local_from, local_to,
                            pence_per_hour, valid_from)
   VALUES ('sports_hall', 'resident', 31, '07:00', '17:00', 3800, DATE '2026-04-01'),
          ('sports_hall', 'resident', 31, '17:00', '22:00', 5000, DATE '2026-04-01'),
          ('sports_hall', 'resident', 96, '08:00', '20:00', 4400, DATE '2026-04-01');
   -- ... one block per kind / hirer type
   COMMIT;
   ```

3. Check for gaps before running it for real. There's a query in
   `tests/db/` (`test_price_rule_coverage`) that checks every bookable space
   has a rule for every opening-hours slot. Run it against a copy of prod.
4. Run it at least a week before 1 April. Bookings made in March for April
   dates are priced on the rule valid *on the booking's date*, so the new
   prices must be in before people start booking April slots.
5. Spot-check a few quotes in the staff "price check" tool.

## "This space has no price for that time"

That's `NoPriceRule`. Nearly always: someone extended opening hours (e.g. a
centre opens at 06:30 now) without adding prices for the new half hour.
Either extend the rule's `local_from`/`local_to` (close + re-insert, as
above) or add a rule for the extra band.

## Out-of-borough residents

Not in the rules. Residents with `is_in_borough = false` pay the resident
rate plus 25% (`OUT_OF_BOROUGH_UPLIFT_PERCENT` in `pricing.py`). If Finance
change that percentage it's a code change, sorry.
