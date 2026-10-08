# Project code

## late_penalty

Helper I wrote for our project's grade tracker. It applies Prof. Chen's homework late policy: 2 free late days, then 20% off per extra day.

```python
def late_penalty(score, days_late, free_days_left=2):
    used = min(days_late, free_days_left)
    charged = days_late - used
    factor = max(0.0, 1 - 0.20 * charged)
    return round(score * factor, 1), free_days_left - used
```

It returns two things: the score after the penalty, and how many free late days are left. Five or more charged days gives a score of 0. Example: `late_penalty(90, 3, 2)` returns `(72.0, 0)`. Not handled yet: negative `days_late` and project milestones (free late days don't apply to the project).
