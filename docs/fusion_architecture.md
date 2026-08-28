# Score-Level Biometric Fusion — Architecture & Build Plan

**Scope:** Steps 1–4 (measure → unlock fingerprint score → plumb → fuse offline).

**Progress:**

| Step | State |
|:--|:--|
| 1 — Offline evaluation harness | ✅ **Done.** See `evaluation/`, report at `evaluation/output/face_eval_report.md` |
| 2 — Firmware confidence | ✅ **Code done, ⚠️ awaiting reflash.** Host side is live and tested; the ESP32 must be flashed before scores appear |
| 2b — Score collection | Not started (needs step 2 flashed + participants) |
| 3 — Score plumbing | ✅ **Done.** `auth/fusion/{quality,scores}.py` + `*_detailed()` methods; all legacy signatures unchanged |
| 4 — Fusion module | Not started (needs 1 + 2b) |

**Explicitly out of scope:** Step 5 (live shadow mode) and Step 6 (letting fusion decide).

**Resolved decisions** (see §9): fingerprint evaluation uses **scores only, collected
from the live R307S** — no images, no templates, nothing biometric leaves the sensor.
ESP32 is available, so step 2 is in scope. New package is `auth/fusion/`;
`auth/fusion_engine.py` is not renamed.

---

## 0. The rules this plan operates under

1. **Additive only.** New files and new optional APIs. No existing function signature
   changes, no existing call site changes, no file deletions.
2. **Nothing decides.** Through step 4, no fusion code sits on any live authentication
   path. It cannot grant or deny anything, because nothing calls it.
3. **Approval gates.** Any deletion, rename, or change to an existing decision path
   stops and asks first. Section 8 lists every gate this plan can foresee.
4. **Green smoke test.** Every step ends with `scripts/smoke_test.py` reporting
   **0 NEW failures**. That is the definition of "didn't break anything".

---

## 1. What the system does today (baseline, verified by reading)

The ATM pipeline in `ui/atm_interface.py::_run_auth_pipeline` runs six sequential
gates. Each is independently thresholded; any failure aborts.

```
Card ──▶ Face ──▶ Liveness ──▶ Fingerprint ──▶ ID Fusion ──▶ Card Owner ──▶ PIN
 │        │          │             │              │              │           │
 │     conf≥X      blinks≥1      match?      face_id==fp_id  face_id==card  hash==
 │
 └─ get_card() → expected_user_id
```

**The "fusion" claim.** `auth/fusion_engine.py` holds subsystems; it performs no
fusion. The actual fusion is one equality test at `ui/atm_interface.py:713`:

```python
if user and user.get("fingerprint_id") == fp_id:
```

That is decision-level AND-gating, not score-level fusion.

### Score inventory (what exists vs. what is thrown away)

| Modality | Produced today | Reaches the decision? |
|:--|:--|:--|
| Face | `final_confidence` = `0.6·(1−cos_dist) + 0.4·vote_conf` (`face_recognizer.py:151`) | ✅ |
| Face | raw cosine distance, `det_score` | ❌ discarded |
| Face | **5 repeated confirmations** collected at `atm_interface.py:544` | ⚠️ mean kept, **spread discarded** (`:547`) |
| Fingerprint (SIFT) | `min(good_matches / 2·threshold, 1)` (`image_matcher.py:250`) | ✅ |
| Fingerprint (R307S) | **nothing** — protocol carries only `MATCH:<id>` | ❌ **does not exist** |
| Liveness | blink count | ✅ as a boolean |
| Liveness | EAR trajectory, min EAR, variance | ❌ discarded |
| Card / PIN | boolean | ✅ correctly boolean |

**The blocking fact:** `config.SOFTWARE_FINGERPRINT = False` is the default, so on the
deployed configuration the fingerprint modality emits **no score at all**. Step 2 exists
to fix that.

---

## 2. Design decision: what gets fused and what does not

This is the load-bearing architectural choice and belongs in the paper.

| Class | Factors | Rule |
|:--|:--|:--|
| **Veto** | Card valid · Liveness · PIN · **Identity agreement** | Failure ends the session. No score compensates. |
| **Fused** | Face + Fingerprint | Normalised, weighted, combined into one biometric confidence, compared to one threshold. |

**Why liveness stays a veto.** If liveness became a weighted term, a high face score
could outvote a failed blink — reinstating exactly the photo attack closed on
2026-08-02 (see `CHANGE_LOG.md`). Compensatory fusion is only safe among factors that
measure *the same thing* (is this the right person). Liveness measures something
different (is this a person at all).

**Why identity agreement stays a veto.** `face_id == fp_id == card_user` is what
defeats "stolen fingerprint + different face". Fusion replaces the *independent
thresholds on each modality*, never the agreement logic.

**Why PIN stays a veto.** A knowledge factor is binary. There is no partial credit.

---

## 3. Target file layout

Everything below is **new**. Nothing existing moves.

```
Final/
├── evaluation/                     ← NEW package (step 1 + step 4 analysis)
│   ├── __init__.py
│   ├── extract.py                  # slow, run-once: dataset → per-sample CSV/NPY cache
│   ├── pairs.py                    # genuine / impostor pair construction
│   ├── metrics.py                  # ROC, AUC, EER, FAR/FRR sweep, d′
│   ├── protocols.py                # Protocol A (pairwise) + Protocol B (system rule)
│   ├── collect_fp_scores.py        # step 2b: interactive R307S score capture
│   ├── face_eval.py                # step 1 entry point
│   ├── fusion_eval.py              # step 4 entry point
│   ├── plots.py                    # matplotlib figures for the paper
│   ├── data/                       # COLLECTED measurements — committed
│   │   └── fp_scores.csv           #   integers only, no biometric content
│   └── output/                     # REGENERABLE figures/CSV/NPY  (gitignored)
│
├── auth/
│   ├── fusion_engine.py            ← UNTOUCHED (existing subsystem holder)
│   ├── risk_engine.py              ← UNTOUCHED
│   └── fusion/                     ← NEW package (step 4 core)
│       ├── __init__.py
│       ├── scores.py               # ModalityScore, FusionInput, FusionResult dataclasses
│       ├── quality.py              # per-sample quality metrics (pure functions)
│       ├── normalize.py            # minmax | zscore | tanh | likelihood-ratio
│       └── combine.py              # equal | dprime-tuned | quality-adaptive weighting
│
├── tests/
│   └── test_fusion.py              ← NEW (plain-script style, matches test_liveness.py)
│
├── config.py                       ← APPEND a new section (existing values untouched)
├── .gitignore                      ← APPEND  evaluation/output/
├── fingerprint_module/
│   └── serial_handler.py           ← ADD a method + attribute (existing method unchanged)
└── esp32/fingerprint_auth/
    └── fingerprint_auth.ino        ← ONE added print (step 2)
```

**Naming note.** `auth/fusion/` sits next to `auth/fusion_engine.py`, which does not do
fusion. Python handles this fine, but it reads oddly. Renaming `fusion_engine.py` to
something honest (`subsystems.py`) is an **approval-gated** change and is *not* part of
this plan — flagged in §8 for a later decision.

**Entry points.** Modules run as `python -m evaluation.face_eval`, so **`main.py` is not
touched**. Adding `--eval-face` CLI flags is optional and deferred (§8).

---

## 4. Step-by-step architecture

### Step 1 — Offline evaluation harness

**Goal:** turn `docs/testing_strategy.md`'s empty checkboxes into measured numbers, and
produce the score distributions that step 4's normalisation mathematically requires.

**Input:** `dataset/USR001..USR021/*.jpg` — 21 users × 20 images = **420 samples**.

**1a. `extract.py` — the slow pass, run once.**
Re-runs InsightFace over all 420 images and caches per-sample:

| Field | Source | Later used for |
|:--|:--|:--|
| `user_id`, `filename` | path | grouping |
| `embedding` (512-d) | `face.normed_embedding` | all distance work |
| `det_score` | InsightFace | quality weight |
| `bbox_area` | `face.bbox` | quality (subject distance) |
| `blur_var` | Laplacian variance | quality |
| `luma_mean`, `luma_std` | grayscale stats | quality (dark / backlit) |
| `ear` | MediaPipe | liveness study, open-eye filtering |

Writes `evaluation/output/face_samples.csv` + `face_embeddings.npy`. ~420 × ~0.3 s ≈ **2
minutes**, once. Every later analysis reads the cache and runs in seconds — this split is
what makes iterating on the analysis practical.

**1b. `pairs.py` + two evaluation protocols.** This distinction is the methodological
core:

- **Protocol A — pairwise (1:1).** Every image against every other.
  → 21 × C(20,2) = **3,990 genuine** pairs, C(21,2) × 400 = **84,000 impostor** pairs.
  Measures *the ArcFace embedding*. Comparable to published literature.

- **Protocol B — system rule (leave-one-image-out).** Hold out one image as the probe;
  the other 19 of that user plus all 20 of every other user form the gallery. Then run
  the **real decision logic** — min distance, the 0.40 tolerance gate, the voting count,
  the `0.6/0.4` blend, and the `MIN_FACE_CONFIDENCE` floor.
  → 420 genuine trials + 420 open-set impostor trials (each probe vs. a gallery with its
  own user removed entirely).
  Measures **your deployed system**, not just the model.

Protocol B is what makes the following two findings testable rather than theoretical:

- Whether `RISK_HIGH_FACE_MIN_CONFIDENCE = 0.75` is inert. Arithmetic says any match
  clearing the 0.40 gate with `vote_conf = 1.0` yields `≥ 0.6(0.60) + 0.4 = 0.76 > 0.75`,
  so the "stricter check" can essentially never reject. Protocol B measures how often
  that actually holds.
- Whether the `0.6 / 0.4` blend weights are well chosen — sweep them and see.

**1c. `metrics.py`.** ROC, AUC, EER, FAR/FRR-vs-threshold sweep, d′ (separation between
genuine and impostor distributions — later reused for tuned fusion weights in step 4).

**1d. `plots.py`.** Distribution histograms, ROC/DET curves, threshold sweep with the
current 0.40 marked. Saved to `evaluation/output/` for the paper.

> **⚠️ Methodological caveat to state in the paper.** All 20 images per user come from a
> single capture session — same lighting, same day, same appearance. Genuine pairs are
> therefore *optimistically* similar and the measured FRR will be a **lower bound**.
> Honest reporting of this is worth more than an inflated number. Cross-session capture
> is the fix, and is a legitimate "future work" item.

**Touches existing code:** none. **Risk:** none.

---

### Step 2 — Recover the fingerprint confidence score

**The finding.** `esp32/fingerprint_auth/fingerprint_auth.ino:248` calls
`finger.fingerSearch()`. The Adafruit library populates **both** `finger.fingerID` and
`finger.confidence` from that call. Line 253–254 prints only the ID. The score is
computed by the sensor and discarded in firmware.

**Protocol change (backward compatible in *both* directions):**

```
old:  MATCH:<id>
new:  MATCH:<id>:<confidence>
```

- *New firmware → old parser:* `serial_handler.py:329` does
  `int(response.split(":")[1])` → `int("12")` on `"MATCH:12:145"`. **Still works.**
- *Old firmware → new parser:* the third field is absent → confidence `None`. **Still
  works.**

That two-way compatibility means the firmware and the Python side can be updated
independently, in either order.

**Python side — signature preservation.** `request_fingerprint_scan()` returns a
2-tuple, unpacked at `ui/atm_interface.py:681`. Changing it to a 3-tuple would break that
call site. Instead:

- keep `request_fingerprint_scan()` byte-identical in signature and return value;
- store the parsed confidence on the handler as `self.last_match_confidence`;
- add a new `request_fingerprint_scan_detailed()` returning the richer result, which the
  old method delegates to.

Existing callers are untouched and cannot notice the change.

> **⚠️ Dependency.** The firmware change requires physically re-flashing the ESP32 and
> **cannot be verified without the hardware**. Steps 1, 3 and 4 are deliberately designed
> not to block on it.

**Touches existing code:** one added `Serial.print` in the `.ino`; one widened parser
branch; one added method. **Risk:** low.

---

### Step 2b — Fingerprint score collection (privacy-preserving)

**The privacy guarantee, stated up front.** The R307S performs matching **inside the
sensor**. Enrolled templates live in its internal flash and are never read out. This
step extracts exactly one thing per trial: **an integer confidence score**. No images,
no templates, no raw biometric data. A fingerprint cannot be reconstructed from the
number `152`.

The sensor's template-extraction command (`getModel()`) is **never called** by anything
in this plan. Raw image upload is not implemented either. See §7.

**What already holds today, unchanged:** `database/users.db` stores only
`fingerprint_id` — an integer 1–127. No fingerprint data is in the database now, and
none is added.

**Trial design.** Two distributions are needed:

| Trial type | How it is produced | Who is needed |
|:--|:--|:--|
| **Genuine** | Participant presses their **enrolled** finger | that specific person |
| **Impostor** | Anyone presses a **non-enrolled finger** (e.g. another of their own fingers) | *anyone* |

The second row is the useful trick: **impostor trials need any non-enrolled finger, not
a new person.** Each participant has nine other fingers. This decouples the logistics —
genuine trials require the specific 21 people, impostor trials do not, so the two halves
can be collected independently and at different times.

Suggested volume: ~5 presses of the enrolled finger and ~10 presses across 2–3
non-enrolled fingers, per participant. Roughly 2 minutes each.

**Recorded per trial — and nothing else:**

```
trial_type,matched,confidence,participant_idx
genuine,1,152,7
impostor,0,,3          ← censored: NOTFOUND, sensor reports no score
impostor,1,88,3        ← FALSE ACCEPT, with a score — the valuable case
```

`participant_idx` is a per-session index, **not** a `user_id`, so the file cannot be
joined back to a named account. Output lands in `evaluation/data/fp_scores.csv`, which is
safe to commit and supports the paper's artifact-availability claim.

> **⚠️ Known measurement limitation — score censoring.** When `fingerSearch()` returns
> `NOTFOUND`, no usable confidence is reported. Impostor scores below the sensor's
> internal threshold are therefore **censored**, and only the right tail is observable.
> This is tolerable: the right tail is exactly the region that determines FAR. It must be
> reported as a censored distribution, not silently treated as complete. The R307
> protocol supports a configurable security level; if the installed library exposes it,
> lowering it during collection widens the observable range — **worth checking, not yet
> confirmed.**

**Consent note for the paper.** These 21 people enrolled to *use* the system; generating
research data is arguably a new purpose. One line stating that participants were informed
and that only non-identifying aggregate scores were retained costs nothing and forestalls
an obvious viva question.

**Fallback if participants are unavailable.** Collect whatever genuine trials are
practical, gather impostor trials from any available non-enrolled fingers, and if the
genuine sample is too thin, fall back to face-only fusion for now (§9, Q1 option d). Step
4's module is designed to degrade gracefully when a modality is missing.

**Touches existing code:** none — new script, uses the step-2 API. **Risk:** none to the
codebase; the risk here is logistical, not technical.

---

### Step 3 — Score plumbing (carry what already exists)

**Goal:** make the scores and quality metrics *available*. Nothing consumes them yet.

The rule throughout: **existing methods keep their exact signatures; richer data flows
through new parallel APIs.**

| Where | Today | Added | Existing callers affected |
|:--|:--|:--|:--|
| `face_recognizer.py` | `recognize_from_frame()` → 3-tuple | `recognize_from_frame_detailed()` → rich object; old method delegates | **none** (`atm_interface:538`, `auth.py:345`, `auth.py:398` unchanged) |
| `atm_interface.py` | 5 confirmations collected `:544`, `np.mean` at `:547` | also compute std/spread of the same already-collected list | none — the list is already there |
| `liveness_detector.py` | blink count only | EAR trajectory accessor (min, variance, face-seen ratio) | none |
| `image_matcher.py` | `match()` → 3-tuple | keypoint count exposed alongside | none |
| `auth/fusion/quality.py` | — | **new** pure functions: frame + face → quality dict | n/a |

**`quality.py` contract.** Pure functions, no I/O, no config reads at call time,
deterministic. Input: a BGR frame and (optionally) the detected face object. Output: a
plain dict of floats. This is what makes it trivially unit-testable and impossible to
break anything with.

**Touches existing code:** additive methods/attributes only. **Risk:** low.

---

### Step 4 — The fusion module + offline comparison

**Goal:** a self-contained, dependency-free fusion engine, evaluated entirely offline.

**`auth/fusion/scores.py` — the contract.**

```
ModalityScore   : name, raw_score, quality (dict), available (bool)
FusionInput     : list[ModalityScore] + context
FusionResult    : fused_score, per-modality normalised scores, weights used,
                  would_be_verdict, strategy name
```

Pure dataclasses. No DB, no config side effects, no I/O. **Nothing imports this from a
live path in this scope.**

**`normalize.py` — four strategies.** Raw scores are not comparable: face similarity
lives in ~0.6–0.9, SIFT good-match counts in 0–200.

| Strategy | Notes |
|:--|:--|
| `minmax` | baseline; outlier-sensitive |
| `zscore` | assumes normality |
| `tanh` (Hampel) | robust; standard in the fusion literature |
| **`likelihood_ratio`** ⭐ | maps a raw score to *P(genuine \| score)* using the distributions **measured in step 1** |

The likelihood-ratio path is why step 1 is a prerequisite, not a parallel task — it
consumes step 1's output directly. The other three are baselines for the ablation table.

**`combine.py` — three weighting strategies.**

| Strategy | Description |
|:--|:--|
| `equal` | 50/50 baseline |
| `dprime` | weight ∝ each modality's measured discriminability (from step 1) |
| **`quality_adaptive`** ⭐ | per-attempt weights modulated by sample quality, renormalised |

Quality-adaptive is the novel contribution: *a blurry face in a dark vestibule should not
get the same vote as a sharp, well-lit one.* When face quality drops, weight shifts to
the fingerprint, and vice versa.

**Graceful degradation.** When a modality is unavailable (`available=False` — e.g. old
firmware, no fingerprint score), weights renormalise over what remains. The system must
never silently treat "missing" as "scored zero".

> **⚠️ Methodological assumption — modality independence.** Face scores come from the 420
> dataset images (step 1); fingerprint scores come from the hardware session (step 2b).
> They are **not from the same trials**, so fusion evaluation must pair them by sampling
> independently from each measured distribution. This assumes face and fingerprint scores
> are statistically independent — the standard assumption in the fusion literature, and
> roughly true since the two sensors fail for unrelated reasons. **It must be stated
> explicitly in the paper**, because it is the first thing a reviewer will probe.
>
> The stronger alternative is a *paired* session where the same person completes face and
> fingerprint in one trial, giving genuinely correlated pairs. More work; worth doing only
> if the independent-sampling result looks promising.

**`evaluation/fusion_eval.py` — the deliverable table.** All approaches compared **at a
matched operating point** (fixed FAR), because comparing at different security levels is
meaningless:

| Approach | FRR @ FAR = 0.1% |
|:--|:--|
| Cascade (current AND-gate) | ? |
| Fusion — equal weights | ? |
| Fusion — d′-tuned | ? |
| Fusion — quality-adaptive | ? |

A negative result (quality-adaptive loses) is still a publishable finding and should be
reported as such.

**`config.py` — new section, appended.** Every value inert by default:

```
FUSION_ENABLED         = False   # master switch, off
FUSION_SHADOW_LOGGING  = False   # step 5, not built yet
FUSION_DECIDES         = False   # step 6, not built yet
FUSION_NORMALIZER      = "likelihood_ratio"
FUSION_WEIGHT_STRATEGY = "quality_adaptive"
FUSION_BASE_WEIGHTS    = {...}
```

Two separate switches for logging and deciding, so enabling observation can never
accidentally hand over control. No existing config value is modified.

**Touches existing code:** appends a config section. **Risk:** none (nothing calls it).

---

## 5. Testing strategy

Follows the existing convention — pytest is not installed, so tests are plain scripts
that stay pytest-compatible (`tests/test_liveness.py` is the template).

| Layer | What |
|:--|:--|
| `tests/test_fusion.py` | normalisers are monotonic and bounded; weights sum to 1; graceful degradation when a modality is missing; known input → known fused score; quality-adaptive reduces to `equal` when all qualities are equal |
| `scripts/smoke_test.py` | **append** `@check`-decorated cases: `auth.fusion` imports cleanly; `evaluation` imports cleanly; fusion config keys exist and default to off |
| Regression | full smoke run after **every** step; requirement is **0 NEW failures** |

`.smoke_baseline.json` is currently `{}` — everything passes today. That is the bar to
hold.

---

## 6. Build order and dependencies

```
Step 1 (eval harness) ─────────────────┬──────▶ Step 4 (fusion + comparison)
                                       │        needs step 1 + step 2b distributions
Step 3 (score plumbing) ───────────────┤
                                       │
Step 2 (firmware) ──▶ Step 2b (collect)┘
   ⚠ needs reflash      ⚠ needs participants
```

Recommended sequence: **1 → 2 → 3 → 2b → 4.**

Rationale: step 1 delivers paper-usable results on its own, so value lands early even if
everything after it stalls. Step 2 is placed early because the reflash is quick and
unblocks the collection session, which is the only calendar-dependent item in the plan —
it needs people, not just code. Step 3 slots in while collection is being scheduled.

**Only step 4 depends on 2b.** If the collection session slips, steps 1–3 still complete
and the fusion module can be built and unit-tested against face scores alone.

---

## 7. What this plan will NOT touch

Stated explicitly so it can be checked against the diff:

- `dataset/` — read-only. No images added, moved, or deleted.
- `encodings/face_encodings.pkl` — read-only.
- `database/users.db` — **not read, not written, not migrated.** No DB changes in steps 1–4.
- **R307S sensor flash** — enrolled templates are never extracted. `getModel()` is not
  called. Raw image upload is not implemented. Only integer confidence scores are read.
- **No fingerprint images or templates are written to disk anywhere**, at any step.
- `ui/atm_interface.py` decision flow — no branch, threshold, or ordering changed.
- `webapp/` — untouched entirely (backend and frontend).
- `auth/fusion_engine.py`, `auth/risk_engine.py` — untouched.
- Any existing function signature or return type.
- Any existing `config.py` value.

---

## 8. Approval gates

Per the standing rule, these stop and ask before proceeding. **None are required for
steps 1–4 as designed** — they are listed so the boundary is explicit.

| # | Item | Status |
|:--|:--|:--|
| 1 | Renaming `auth/fusion_engine.py` → something honest | **Not in this plan.** Would need approval. |
| 2 | Re-flashing the ESP32 (step 2) | ✅ **Approved** — hardware available. |
| 3 | Changing any existing return signature | Avoided by design. Would need approval. |
| 4 | Adding `--eval-*` flags to `main.py` | Deferred; `python -m` needs no change. |
| 5 | Extracting fingerprint templates or images from the sensor | ❌ **Ruled out.** Never done. |
| 6 | Anything in step 5/6 (live shadow, flipping the decision) | Out of scope entirely. |
| 7 | Running the participant collection session (step 2b) | Needs scheduling — logistical, not technical. |

---

## 9. Decisions on record

**Q1 — Fingerprint evaluation data. ✅ RESOLVED: scores only, from the live R307S.**

`fingerprint_dataset/` is empty and `SOFTWARE_FINGERPRINT = False`, so the fingerprint
modality had no score source. Options considered:

- ~~(a) Download SOCOFing~~ — rejected. Generic public data; measures someone else's
  sensor, not the deployment.
- **(b) Collect from the R307S — SELECTED**, in its *scores-only* variant (§Step 2b).
  Nothing biometric leaves the sensor. This is **stronger** than (a) for the paper: it
  characterises the actual deployed hardware.
- ~~(c) Simulate from published R307S characteristics~~ — rejected as unnecessary once
  (b) was viable. Retained as a fallback only.
- ~~(d) Face-only~~ — retained as the fallback if the collection session cannot happen.

**Q2 — ESP32 availability. ✅ RESOLVED: available now.** Step 2 is in scope and is
sequenced early, because it unblocks step 2b.

**Q3 — Package naming. ✅ RESOLVED: `auth/fusion/`.** `auth/fusion_engine.py` is not
renamed and not touched. Revisit only if the ambiguity becomes a real nuisance.

**Q4 — Scope. ✅ Steps 1–4 only.** Shadow mode (5) and letting fusion decide (6) stay
out. Steps 1–4 produce a complete, paper-ready contribution with **zero** change to live
authentication behaviour.

### Still open — logistical only

**L1 — Scheduling the collection session.** Genuine trials need the specific 21
participants; impostor trials need only any non-enrolled finger, so the two halves can be
collected separately (§Step 2b). Nothing in steps 1–3 blocks on this.

**L2 — R307 security-level configurability. ✅ RESOLVED: it is exposed.**
The installed library at
`C:\Users\Shubh Parmar\Documents\Arduino\libraries\Adafruit_Fingerprint_Sensor_Library`
declares `uint8_t setSecurityLevel(uint8_t level)` (`Adafruit_Fingerprint.h:193`) with
levels 1–5 (`:112-116`). Lowering it during collection would widen the observable
impostor range and reduce censoring.

> ⚠️ **Not implemented, and deliberately so.** The security level is *persistent sensor
> state*: lowering it makes live matching more permissive, and forgetting to restore it
> would silently weaken production authentication. Adding a `SECURITY:<level>` command is
> therefore an **approval-gated decision at step 2b**, not a step-2 change. If taken up,
> it needs a read-back so the level can be verified and restored afterwards.

**L3 — The ESP32 still needs flashing.** Step 2's firmware change is written but the
board has not been re-flashed. Until it is, `MATCH:` lines carry no score and
`last_match_confidence` stays `None` — which the host handles correctly, but which means
step 2b cannot collect anything yet.

---

*Design authored before implementation. No code has been written against this plan yet.*
