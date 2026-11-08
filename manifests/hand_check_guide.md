# How to check the hand-worked cases yourself

You need paper or a spreadsheet and about an hour. You're checking two separate things:

1. **Arithmetic:** do the rules, applied by hand, give the recorded answers?
2. **Semantics:** are the rules the right ones for this paper? Only you can judge this, and it matters more. Two programs and two blind agents can all agree on a rule that shouldn't be there.

Work each case before opening the answers. The full rules are in sections 7 to 9 of `spec/workflow_semantics_v1.md`. The card below is enough for these cases.

## Rule card

**The small model.** All times are seconds from Monday 00:00. Working hours are Monday to Friday, 09:00 to 17:00.

```text
Start -> Review -> decision G -> rework: back to Review (new visit)
                              -> ok: wait 300 s (timer) -> Decide and Notify in parallel -> both done -> End
```

| Task | Who does it | Work needed |
|---|---|---|
| Review | Clerk_0 or Clerk_1 | 600 s |
| Decide | Officer_0 | 1200 s |
| Notify | Clerk_0 or Clerk_1 | 300 s |

**Useful times:** 32400 is Monday 09:00. 406800 is Friday 17:00. 637200 is the next Monday 09:00.

**Rules, in order:**

1. **Whose turn:** among tasks waiting to be assigned, take the smallest enabled time. On a tie, take the case that arrived first, then the lower case id, then the lower task id. `T_decide` comes before `T_notify`.
2. **Who does it:** give the task to the worker who can start earliest. On a tie, take the worker free for longest, meaning the smallest free-at time. If still tied, take the lower number.
3. **When it finishes:** count only working time. If a worker is off during the task, the task pauses and stays with that worker. The worker is held until it finishes.
4. **Routes:** take `rework` if the draw is below the rework probability, otherwise `ok`. Draws never change. Only the probability does.
5. **Timer:** the 300 s wait needs no worker and ignores working hours.
6. **Case end:** the later of Decide and Notify.

Each task gets assigned as soon as it's its turn, even if it starts later. Its finish time then creates whatever comes next.

## Worked start, using H01

Arrivals: c0000 at 32400, c0001 at 32700, c0002 at 33000. Draws at G: c0000 is 0.1 then 0.9, c0001 is 0.4 then 0.8, c0002 is 0.9. Rework probability is 0.25.

| Step | Task | Worker choice | Result |
|---|---|---|---|
| 1 | c0000 Review, enabled 32400 | Both can start at 32400 and both have free-at 0, so the lower number wins: Clerk_0 | Runs 32400 to 33000. Draw 0.1 is below 0.25, so rework: Review visit 2 is enabled at 33000 |
| 2 | c0001 Review, enabled 32700 | Clerk_0 can start at 33000, Clerk_1 at 32700: Clerk_1 | Runs 32700 to 33300. Draw 0.4 is not below 0.25, so ok: timer 33300 to 33600. Decide and Notify are enabled at 33600 |
| 3 | Tie at 33000: c0000 Review visit 2 and c0002 Review | c0000 arrived first, so it goes first | Continue from here |

Finish H01 yourself. It gives you the baseline for the other three.

## Cases to work

Write one row per task: case, task, visit, enabled, start, end, worker. Also write each case's end time.

### H02: a worker becomes unavailable during a task

Same as H01, but Officer_0 is unavailable from 34000 to 34600.

- **Check:** which task is running at 34000, when does it finish, and how does that push back the next two Decide tasks?
- **Judge:** the running task pauses and resumes with the same worker. Alternatives would be to let it finish first, or to hand it to someone else. Is pausing the behaviour you want the paper to rest on?

### H10: changing a routing probability keeps the draw

Same as H01, but the rework probability is 0.5, and `ok` is also 0.5.

- **Check:** only c0001's first draw (0.4) changes outcome, because it sits between 0.25 and 0.5. c0000 and c0002 keep their routes, though their times shift. c0001's second visit uses its own draw, 0.8.
- **Judge:** this is your condition 3. Confirm it matches what you meant.

### H15: calendar edges and added cases

Base run has 1 case, c0000, arriving at 32400, draw 0.9. Add x1 arriving Friday 16:50 (406200) and x2 arriving Friday 16:55 (406500), both with draw 0.9.

- **Check:** x1's Review ends exactly at closing time, 406800. x2's Review pauses over the weekend and resumes Monday. Both timers run on, ignoring working hours, including outside them.
- **Judge:** should a timer keep running over a weekend? The published simulator's code does this too, and we kept it. Added cases don't have to arrive inside the arrival calendar. Is that acceptable?

## Comparing with the answers

Answers are in `validation/hand_worked_expected.json`. Find the case by its full name, such as `H02_unavailable_pauses_running_task`. Task rows read: case, task, visit, enabled, start, end, worker, work needed. Case rows read: case, then arrival and end.

When a row differs, the cause is one of three things:

| What you find | Meaning | What to do |
|---|---|---|
| You misapplied a rule | Your slip | Nothing |
| You applied a rule as written and got a different answer | Possible error in my hand-worked answer. Both programs also agree with that answer, so this would be a serious finding | Tell me the case and row |
| The rule is clear, but you think it's wrong | A semantic decision | Tell me which rule and what you'd prefer |

## Other rules worth a look

These aren't exercised directly by the three cases, but they shape every result:

- **One shared queue per pool:** a Clerk's Review and Notify tasks wait in one first-come-first-served line.
- **Longest-idle worker first:** this affects which worker's unavailability matters.
- **`count` removes the highest-numbered workers:** "one fewer Technician" always means the same person.
- **Whole seconds:** all durations are rounded to whole seconds.
- **Service plans are known:** the benchmark gives systems each case's required work and draws. This is a controlled assumption, not a claim about real operations.

Any change to a rule means I update the spec, both implementations and the affected answers, then rerun all comparisons. It's cheapest before the Nov 9 freeze.
