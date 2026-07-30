# Price Rounding Rules

All recommended prices must end in .49 or .99, matching the pricing
convention customers already associate with this business. A recommended
price that doesn't land on one of those endings should be rounded to the
nearest allowed ending.

Rounding must never be applied in the direction that pushes a price below
its category's minimum margin floor (see the margin policy). If rounding
down would violate the floor, round up to the next allowed ending instead,
even if that ending is numerically farther from the raw optimizer output.

Price increases of more than 15% in a single change should be phased over
at least two pricing cycles rather than applied all at once, regardless of
what the optimizer's unconstrained output suggests.
