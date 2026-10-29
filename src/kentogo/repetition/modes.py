"""The choices of the spaced repetition, shared by the quiz and the seichi practice.

Their settings are kept by each practice (review.review_settings, seichi.seichi_settings).
"""

# Which are asked first: those never asked, or those to ask again.
PRIORITY_NEW = "new_first"
PRIORITY_REVIEW = "review_first"
PRIORITY_MIX = "mix"  # Two reviews, then one new one, and so on (see plan.MIX_REVIEWS).
PRIORITIES = (PRIORITY_NEW, PRIORITY_REVIEW, PRIORITY_MIX)

# How those answered wrong are asked again.
REVIEW_CURVE = "curve"  # Along the forgetting curve, until enough correct reviews in a row.
REVIEW_ONCE = "once"  # Asked again until answered correctly once.
REVIEW_MODES = (REVIEW_CURVE, REVIEW_ONCE)
