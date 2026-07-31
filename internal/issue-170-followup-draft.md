# POSTED — issue #170 follow-up

Posted 2026-07-30 01:22 UTC:
https://github.com/vishalsachdev/canvas-mcp/issues/170#issuecomment-5125231050

Kept as the record of what was published. Do NOT re-post. The body below the
rule is exactly what went out (this header was stripped).

---

Thanks for the follow-up, and for testing against a real deployment plan rather
than a hypothetical one. Summarizing what I took from the feedback, plus the
per-course design, which changed shape once I tried to make it actually hold up.

Tier 1 is implemented and tested on a branch. Details below so you can push back
before it lands.

## 1. Narrowed sequencing

Tier 1 scope and the `STUDENT_WRITE_TOOLS` operator allowlist are confirmed, so
I resequenced around the actual unblocker:

**First (the pilot unblocker):**
- `get_my_submission` — your own submission, attempts used vs allowed, due and
  lock dates, existing comments
- `submit_assignment` — `online_text_entry`, `online_url`, `online_upload`

**Trailing, same release:**
- `comment_on_my_submission`
- `mark_module_item_done`

`STUDENT_WRITE_TOOLS` still defaults to empty, and a tool you have not named is
never registered at all, so it does not appear in the tool list for an agent to
discover. Quiz-taking remains excluded.

**One change from the list of five I posted earlier.** I had `upload_submission_file`
as a separate tool alongside `submit_assignment`. It is gone, folded into
`submit_assignment` as a `file_paths` / `file_contents` argument, so Tier 1 is
four tools rather than five. Two reasons:

- A separate upload tool can succeed and then never be attached to anything,
  leaving orphaned files in the student's Canvas account with no submission and
  no obvious way for them to notice or clean up.
- More importantly it would route around the confirmation. The upload is part of
  what the student is agreeing to, so it has to sit inside the confirmed
  operation rather than be something an agent can do beforehand on its own.

Nothing is lost in capability: `submit_assignment` with `online_upload` still runs
Canvas's full three-step upload. If you specifically want the upload exposed on
its own for a workflow I have not thought of, say so and I will add it back as a
separate tool.

## 2. Binary-safe file upload, committed and tested

Noted the report about a jpeg getting OCR'd elsewhere with a "text only"
response. That is a design choice, not a Canvas limitation, and it is not how
this works here.

`online_upload` opens the file in binary mode and streams **raw bytes**: no
decode, no transcode, no content inspection, no OCR. The content type is derived
from the extension and passed through. Canvas's real 3-step flow is used, with
step 1 against `/submissions/self/files`.

The test suite includes a real JPEG fixture asserting **byte equality** at the
storage boundary. If a future change ever routes upload content through a string
path, that test fails rather than the behavior quietly degrading in production.

On which types are accepted: there is deliberately **no** global extension
allowlist. I had one initially and removed it, because it rejected ordinary
student work (`.heic`, which is every iPhone photo, and `.tex`) and because it
was the wrong authority in the first place. The assignment's own
`allowed_extensions` is the instructor's actual statement of what that assignment
takes, so that is what gets enforced, and the error tells the student which types
*are* accepted. Filenames are still sanitized, since a malicious path is a real
attack whereas an unusual extension is not. Limits are 100 MB per file, and
100 MB across at most 20 files per submission, checked before anything is decoded.

**One thing that matters specifically for your deployment.** Since you are
running a central HTTP service, a `file_paths` parameter naming a path on the
*server* would be both useless to your users and a genuine hole: a remote caller
could name any file the server process can read and upload it into their own
Canvas submission. So local paths are **refused outright over HTTP transport**.
Hosted callers pass `file_contents` with base64 instead, with a size bound
applied before decoding. Local stdio users keep the path form, where it is
correct.

## 3. Per-course instructor control

This is the right requirement, and I agree with the framing: half
change-management (faculty need to know the capability exists and that they have
a lever) and half technical (constraining agent activity to the course and
function level).

Your deployment constraint drives the shape. A central service on a platform
that handles configuration without custom code means per-course policy cannot
live in your infrastructure, because there is nowhere to put it. It has to live
in the library so it behaves identically on stdio, on our hosted instance, and
on your platform.

### What I proposed first, and why I changed it

My first instinct was a conventionally-named course **Page**, guarded by
requiring its `editing_roles` to be teacher-only. A review pass killed it, and
the reason is worth stating because it would have been a real hole.

`editing_roles` tells you who may edit a page *now*, not who wrote it. Canvas
Pages can be set to `teachers`, `students`, `members` or `public`, and in many
courses a student can create a page before any instructor does — including
creating the policy page with `agent_writes: allow` and setting it teacher-only
in the same breath, locking themselves out *after* authoring the content meant to
bind them. Since the policy is read using the **student's own token**, authorship
cannot be established at all. So a page cannot be trustworthy here however it is
screened, and I removed the option rather than ship a second, knowingly-weaker
authorization path beside a sound one.

### What it actually is: the course syllabus

The policy is read from `syllabus_body`. Under every standard Canvas role,
students can read the syllabus and cannot edit it, so instructor authorship is
*structural* rather than assumed. It needs no new infrastructure, it travels
with course copy, and it is the same API read everywhere.

An instructor writes one line:

```
agent_writes: deny
```

or, to allow with limits:

```
agent_writes: allow
allow_tools: submit_assignment
note: Allowed for the weekly labs. Ask me before using it on the final project.
```

`note` is surfaced to the student when a write is blocked, so a refusal explains
itself instead of looking like a bug. Parsing is `key: value` lines after
HTML-to-text, so it survives the Canvas rich-text editor.

The syllabus is the **only** carrier — there is deliberately no config knob to
select a weaker one.

If keeping this out of the syllabus turns out to matter to you, say so and we can
look at an instructor-only artifact students cannot create at all (a
no-submission assignment is the obvious candidate). I would rather hear that
requirement than invent a mechanism nobody asked for.

### Failure posture

Only a definitively read, well-formed policy can grant:

- Malformed policy → **deny** (a typo must never become a grant)
- Contradictory directives → **deny**. If `agent_writes: deny` appears anywhere,
  an earlier `allow` cannot override it. An appended revocation being silently
  discarded is the worst direction for this to fail.
- Read failure, permission error, Canvas outage → **deny** (an outage must not
  silently grant writes across every course)
- A course this caller cannot see → **deny**, and never cached. Canvas answers
  404 both for "does not exist" and "you cannot see this", so caching that
  verdict per course would let one caller without access install an answer for
  everyone — and under a permissive default, override an instructor's denial.
- Genuinely absent (the course reads fine and states nothing) → the configured
  default (section 4). This is the only absence that is cached, because it is
  the only one that is caller-independent.

Grants are cached ~30s, denials ~5min. The asymmetry is deliberate: a stale
grant is a revocation window on an action that spends a student's limited
attempts, while a stale denial is merely inconvenient. Policy is re-checked
immediately before the write itself, not only at preview.

### The change-management half

No amount of code fixes discoverability. Faculty have to know the lever exists.
The practical mitigation is operator-side: seed the `agent_writes:` line into
your course templates or Canvas blueprint so every course ships with it present
and the instructor only edits one word. Happy to provide a template snippet and
a short faculty-facing explainer so campuses are not writing that from scratch.

## 4. A question for you: default posture

The one decision I do not want to make unilaterally, because it is institutional
policy rather than engineering:

**When a course states no policy at all, what should happen?**

- **deny-by-default** (currently the shipped default) — no student write works
  anywhere until an instructor opts their course in. Faculty who never engage
  are protected by inaction. Cost: pro-AI instructors must act first, and early
  pilot sessions will mostly be students hitting a wall.
- **allow-by-default**, within the operator allowlist — usable immediately.
  Cost: reserved faculty are unprotected until they act, and they are exactly
  the population least likely to act.

It ships as `COURSE_AGENT_POLICY_DEFAULT` either way, so each campus picks. But
I would like to know which **you** want for your pilot, because that is the one
I will document as recommended and the one that will actually get exercised.

## 5. Layering, stated plainly

Two gates, one direction:

1. `STUDENT_WRITE_TOOLS` is the **campus-wide operator ceiling**.
2. A course policy can only **further restrict within it**. Never expand it.

Effective permission is the intersection. An instructor naming a tool the
operator never enabled gets nothing, with no path that could be mistaken for
success. Central IT keeps the outer boundary; faculty get agency inside it.
There is deliberately no mechanism for a course-level artifact to escalate past
the operator setting.

## 6. Two things I want to flag honestly

**The submit endpoint is not self-scoped.** I said earlier that student writes
are structurally `/self`-scoped. That was wrong for the one that matters:
`POST /courses/:id/assignments/:id/submissions` has no `self` segment, and
Canvas honors `submission[user_id]` there when the token carries grading
permission. Tool *profile* is not proof a token lacks teacher rights, and plenty
of real people hold mixed student and TA enrollments. So the guarantee is now
enforced on the wire instead: every outbound write body is checked against an
identity-override denylist (`submission[user_id]`, `as_user_id`,
`submission[group_id]`, and friends) immediately before it is sent, and a test
asserts the exact permitted field set rather than merely the Python signature.

**Group assignments are refused.** A submission to a group assignment becomes
the group's submission and spends a shared attempt, binding classmates who never
agreed to it. That deserves its own decision rather than a default, so Tier 1
declines and tells the student to submit in Canvas.

## 7. Confirmation is bound to content, not a boolean

I originally described a confirm-before-submit preview. A boolean an agent sets
itself is not really confirmation, so it works like this instead: the first call
previews and issues a short-lived, single-use token bound to the target, a hash
of the payload, and the observed attempt number. The second call must present
that token. An agent therefore cannot submit without first producing a preview,
and cannot submit something other than what was previewed. If another submission
lands in between, the attempt number moves and the token is void rather than
silently spending a second attempt.

## 8. Scheduling

Since the Zoom moved to mid-September, design discussion happens here, which is
better for the record anyway. The two answers that would help most before this
lands:

1. Your default-posture answer (section 4).
2. Your service owner's read on the syllabus as the policy carrier — it means
   the course's stance on agent use is visible to students. I would argue that
   is a feature, but it is a change from "invisible instructor config" and your
   call to make. If it is a blocker, see the note in section 3 about an
   instructor-only alternative.

One operational note for your central deployment. A submission confirmation is
redeemable only on the process that issued it. That is deliberate: the
single-use claim lives in process memory, and a token redeemable on any replica
could be accepted by two workers at once, submitting twice and spending two
attempts. Doing it properly across replicas needs shared atomic state (Redis or
similar), which I do not want to make a requirement of a library people run on
their laptops. So configure session affinity so a student's preview and
confirmation reach the same worker. Without affinity nothing unsafe happens: the
confirmation is rejected and the student previews again.

Quiz questions continue in #172, self-identity (`get_my_enrollments` /
`get_my_profile`) in #171.
