# Tiki Data: ball possession for BAR-ATH

## 1. Approach

We treat possession as **segmentation**, not per-frame classification: `spellF1` matches whole
possessions by temporal IoU, so the shape of each segment matters more than per-frame accuracy. A
change that is a second late, or a possession split in two, costs more than a few wrong frames.

The submitted pipeline (`possession.py`) uses one model learned from open data: who has the ball in live
play, scored per frame and decoded into possessions (`live_model.json`). It also loads
`stops_model.json`, a model for the edges of the stoppages and the team that restarts, but that
model did not pass its confirmation, so the file holds the identity model, which changes no label. The
pipeline runs four steps:

1. **Dead ball**. A frame is `D` when most tracked players are slow, or when the ball is seen
   off the pitch. Slow means below 1.75 m/s for at least 85% of the tracked players in a centred 5 s
   window; the stoppage lasts while the share stays at 75% or more (hysteresis) and counts if it is at
   least 3 s long. Its start then moves 1 s earlier and its end 38 frames earlier, because players slow
   down after the whistle and speed up after the restart. A ball that is missing never counts: in the
   automatic tracking it goes missing by occlusion, so its absence says nothing about a dead ball. Each
   `D` ends a possession, which is the only way to separate two possessions of the same team (`H D H`).
2. **Owner evidence**. Per frame, the team of the nearest tracked player, but only if that
   player is within 1 m of the ball; otherwise the frame has no evidence. While the ball travels in a pass
   the nearest player is often an opponent far from it, and this removes that noise. When the ball is
   missing, its position is a straight line between the last and the next position seen, for gaps of up
   to 2 s; a longer gap has no evidence.
3. **Live-play possession**. Per frame, integer signals of each team:
   - around the ball: its two nearest players, how many are within 3 m and 10 m, and how fast the nearest
     one closes in;
   - its owner evidence from step 2 in the 0.5, 2 and 5 s before and after the frame (the pipeline runs
     offline, so it can look ahead);
   - its block: advance towards the rival goal, width, length and forward speed;
   - the ball: seen or not, how long its gap lasts, its speed.

   Gradient-boosted trees, trained on open data and exported to integer thresholds and leaves, score the
   frame twice, once with each team as the own one. The difference is the frame's score, so the model
   cannot tell which team is the home one. Inside each live stretch, a two-state Viterbi picks the
   sequence of `H` and `A` with the highest summed score minus a fixed cost per change (10 logits, chosen
   on open data). A change that ties across frames is dated to its first frame.
4. **Output.** `H`, `A` or `D` for every frame inside the two halves, `X` outside them.

Why a trained model for live play and rules elsewhere: even with the full ball and the true dead ball, the
earlier change rule (a rival run of 12 frames) reached only 0.740 on Metrica and 0.598
on IDSSE, and possession in live play was the largest gap we measured (+0.34 and +0.48 with it perfect).
The model and the decoder stay deterministic: integer signals, integer trees and an integer Viterbi, so the
CSV is the same byte for byte on any machine (SUBMISSION.md requires it). We also trained a tree-based model
for the stoppage edges and the restart team on open data. It improved IDSSE but not Metrica on
the matches kept aside, so it is not in the submission (section 6). Two later candidates for the stoppage
edges did not reach it either: a physical rule that ends each stoppage at the kick of a still ball
passed all 43 conditions on the open benches but did not change the submitted file (the same `sha256`), and a
learned edge model with Metrica's convention did not pass its confirmation.

## 2. Assets used and dropped

| Asset | Used? | How |
|---|---|---|
| Tactical ATD (tracking) | yes | player and ball positions and player speed |
| Smart Tagging | no, as model input | the team signal comes from the tracking. Once, on 30/10, we ran a script that compares the tags with our own evidence of who owns the ball (an automatic check on the provided data, aggregates only); it changed no parameter, label or file of the pipeline (issue 8). Using the tactical phases as a second team signal is the next step we did not reach; it first needs another match with tags and an independent possession reference to be validated (issue 27 of the official repository) |
| Homography | no | not needed: the tracking is already in pitch coordinates |
| Video (tactical / broadcast) | no | ball detection in video dropped: effort against time |

### How each rule is met

| Rule (organisers' clarification of 03/11 and `RULES.md`) | How the team meets it | Where |
|---|---|---|
| Do not train, fit or calibrate on the ground-truth possession data or on the provided video | The model is trained and its parameters chosen on 10 open matches (Metrica Games 1-3, IDSSE 1-7). The public 5-minute window only checks that the pipeline runs. The ball-missing levels used to degrade the training data were fixed beforehand and none comes from the public ground truth | section 3 |
| No hand labels or human-produced data about the provided game | Labels come from the open datasets (event annotations, the provider's own tracking flags). From the provided game we use the automatic tracking and the two kick-off frames that the official FAQ publishes. Nothing was labelled by hand | section 3 |
| Do not check the output against the video | The video is not used at any step of the pipeline | section 2 |
| Use only external data you have the rights to use | Metrica sample-data (public GitHub repository) and IDSSE (CC BY 4.0, revision `a715a38`), cited in section 3 | section 3 |
| The organisers must be able to access and review the method | The code, the models and the commands are in the public repository; the same `sha256` came out on four machines | section 7 |

## 3. Training and calibration data

Nothing from the provided game: no hand labels, and the public 5-minute window is used only to
check the pipeline, never to choose a parameter. The live-play possession model is trained on
the datasets below:
- chosen leaving one match out at a time on 7 matches (Metrica Games 2-3, IDSSE 1-5);
- confirmed once on the 3 kept aside (Metrica Game 1, IDSSE 6-7);
- retrained on the 10 for the submission.

The same datasets chose and confirmed the parameters of the rules, and trained and tested the stoppage
model that we did not adopt.

| Dataset | Source | Labels: who and how | Amount | Used for |
|---|---|---|---|---|
| Metrica Sample Games 1-3 | [metrica-sports/sample-data](https://github.com/metrica-sports/sample-data) | Metrica's event annotations. Possession is the team of the last on-ball event; dead ball runs from the previous event to the restart | 3 matches, 145,006 / 141,156 / 143,761 frames | training the possession model, choosing parameters (Games 2 and 3) and confirming them (Game 1, kept aside) |
| IDSSE (Bassek et al., *Scientific Data* 12, 195, 2025) | [pysport/idsse-data](https://huggingface.co/datasets/pysport/idsse-data), revision `a715a38`, CC BY 4.0 | dead ball and owning team per frame from the provider's tracking (DFL `BallStatus`, `BallPossession`) | 7 matches (14 halves), 1,002,644 frames | training the possession model, checking the dead-ball labels and confirming the choices on a second provider. The possession model and the stoppage model were selected on matches 1-5 and confirmed on 6-7, kept aside |

The open tracking is clean, unlike the automatic one. We degrade it to look like the automatic tracking
(about 45% of the ball missing in gaps of 1.5 s on average, plus player noise in the robustness checks),
and compare versions with a paired bootstrap of the possessions (`bench.py`). The possession model
trains on four such degradations, from 0% (only what the open tracking already misses) to 45% of the live
ball missing, with the ball of the stoppages kept or missing on half of their frames, each with clean and with
noisy players. None of these levels comes from the public ground truth: they were fixed beforehand.

### Where each constant comes from

Every value that decides a label, with how it was set. "Selection" is Metrica Games 2-3 and IDSSE 1-5; "reserve" is
Metrica Game 1 and IDSSE 6-7, used only to confirm.

| Constant (`possession.py`, `calibrate_live.py`) | Value | How it was set |
|---|---|---|
| `HALVES`, `KICKOFFS` | graded frames 11,185-90,651 and 110,808-190,197; kick-offs 11,185 and 113,742 | published by the organisers (`games.half_video_blocks()`, `FAQ.md`) |
| `PITCH` | 105.3 × 68 m | published by the organisers (`games.py`) |
| `SLOW_CUT`, `SLOW_WINDOW`, `SLOW_ENTER`, `SLOW_STAY`, `SLOW_MIN` | 1.75 m/s, 5 s, 85%, 75%, 3 s | sweep of 459 combinations on Metrica Games 2-3 (seeds 0-9), confirmed on Game 1 (seeds 20-29) |
| `DEAD_LEAD`, `DEAD_TRIM` | stoppage starts 1 s earlier, ends 38 frames earlier | 160 edge settings in the same sweep and confirmation |
| `DEAD_WINDOW`, `OFF_MIN` | ball seen off the pitch in half of a 2 s window, for at least 1 s | kept from the first detector without a sweep; adding the signal was chosen on Metrica Games 2-3 |
| `CONTROL_RADIUS`, `MAX_INTERP` | 1.0 m, 2 s | sweep of 300 combinations on Metrica Games 2-3, start of the stable zone, confirmed on Game 1 (seeds 20-29) |
| `CHANGE_FRAMES`, `MAX_GAP` | 0.5 s, 4 s | same sweep; used only by the fallback mode `rule`, not by the submitted model |
| Live-model signals: `EV_WINDOWS`, player counts, `UNSEEN_CAP`, `MAX_SPEED_CM` | 12, 50 and 125 frames; players within 3 and 10 m; caps of 10 s; speeds over 0.2 s, jumps above 12 m/s dropped | fixed by design before training, not swept |
| Live-model recipe (`live_choice.json`) | 63 leaves; change cost λ = 10 logits (`switch` = 2 · λ · 10^6) | 8 recipes, leaving one selection match out at a time; confirmed on the reserve (43 conditions) |
| `SHORT_S`, `SHORT_WEIGHT` | 5 s, weight 1 | weight 3 lost to weight 1 in the paired protocol (41 of 43 conditions) |
| `TRAIN_BALLS` | live ball missing on 0, 20 and 45% of frames; stoppage ball on 0 or 50%; mean gaps of 1.5 and 3 s; seeds 100-103 | fixed before training: 0 and 50% are the extremes, 45% rounds up the 41% that `DATA.md` publishes |
| `TRAIN_NOISE` | 0.6 m of position noise, 10% of slots lost, identity swaps near the ball on 5% of frames | one of the bench's noise scenarios (`explore/player_noise.py`), fixed before training |
| Bench degradation (`bench.py`) | 45% of the live ball missing, gaps of 1.5 s on average | design default; 45% from `DATA.md`. The gap length is not measured on BAR-ATH, so every decision is also checked with 3 s gaps |
| `stops_model.json` | identity: changes no label | none of its three candidates was adopted (section 1) |

No value was calibrated on the public window's ground truth, and none comes from the Smart Tagging or the video. From the provided game the
pipeline takes only what the organisers publish: the frame ranges, the kick-offs, the pitch size and the 41% of
missing ball. The committed models have `sha256` `1f8b706e0c30e5e0d3e97d69285dd3bbc1ea1b270c8efaa64f6ddf8190b763c1`
(`live_model.json`) and `b2f7aeff5855813cd98521816da6610368e1c16578b2eb0bab06345422b7c368` (`stops_model.json`).

## 4. Possession rules

- **Possession change:** decided by the decoder of section 1. A change costs 10 logits, so it
  needs the model's score to favour the other team for long enough. A change that ties across frames is
  dated to its first frame. The earlier rule (the rival as the evidence for 12 frames) is what `live_model.json` falls back to in mode `rule`.
- **Dead ball:** slow players or the ball seen off the pitch, as in section 1. The labels used
  to calibrate it on open data come from the events: a restart is a set piece or a goal kick, and the dead
  ball runs from the previous event to it.
- **Loose balls and challenges:** no explicit rule. The model sees the nearest players of both teams,
  their speeds and the evidence around the frame. A contest that does not move the score for long enough
  does not pay the cost of a change, so the previous owner is kept.
- **Restarts:** the end of a dead stretch is located from the players speeding up, moved 38 frames
  earlier. After it, the decoder picks the team from the model's score. The restart team of `stops_model.json` is
  not used (section 6).
- **Abstention (`X`):** never inside the halves. The scorer fills each `X` with the previous
  label, which the decoder already holds, so abstaining adds nothing to `spellF1` and lowers `macroF1` by
  up to 0.10.

## 5. Results

On the public window (pipeline check only, 17 possessions; 5-95% bootstrap band in brackets):

| Version | spellF1 | macroF1 |
|---|---|---|
| baseline_smooth125 | 0.4242 [0.27, 0.59] | 0.5812 [0.45, 0.67] |
| nearest player, rule-based dead ball | 0.5294 [0.35, 0.71] | 0.7543 [0.62, 0.84] |
| + dead-ball detector v2 | 0.4941 [0.32, 0.67] | 0.8726 [0.73, 0.91] |
| + control radius, interpolation, change rule | 0.5714 [0.41, 0.72] | 0.8617 [0.73, 0.90] |
| + live-play possession model and decoder | 0.5946 [0.43, 0.75] | 0.8889 [0.76, 0.93] |
| + same model retrained after fixing the open-data speeds across player changes and halves | 0.5622 [0.40, 0.70] | 0.8894 [0.75, 0.93] |
| + dead ball before each kick-off and training balls without public-window levels (submitted) | 0.5939 [0.41, 0.78] | 0.8970 [0.76, 0.94] |

The scorer states that gaps below about 0.28 are within noise at 17 possessions, so this table does
not rank the versions. The choice between them comes from the open-data bench:

| mean spellF1, degraded tracking (last row: paired bootstrap against the row above) | Metrica Games 1-3 (seeds 20-29) | IDSSE (14 halves) |
|---|---|---|
| nearest player, rule-based dead ball | 0.250 | 0.220 |
| + dead-ball detector v2 | 0.405 | 0.339 |
| + control radius, interpolation, change rule | 0.541 (+0.136 [+0.121, +0.152]) | 0.412 (+0.073 [+0.062, +0.085]) |

This table preserves the historical configuration before #52: evidence used
105.3 × 68 m and crowd-dependent degradation used 105 × 68 m. The bench now passes
each match's dimensions explicitly. Sources, revisions and paired
differences are recorded in [Bench geometry](GEOMETRIA-BANCO.md); delivery parameters remain unchanged.

The control radius wins in all three Metrica matches and in all 14 IDSSE halves, with the ball as is
and degraded, and under player noise. That version's file passed `validate_submission.py` and had
`sha256` `9e8a0b36032543582397817e830cc3ac67b2166e2a44d6e71e528441fcbbbeb8`; two machines produced it.
The file of the first live-play model passed `validate_submission.py` and had `sha256` `3a2e8ac577d6c0f8ee43bf9defb6139cf27370143516e9151c987043a38d4385`; two machines produced it. The submitted file is described below.

The live-play possession model is trained on these matches, so it is measured on the matches it did not
see before its confirmation: Metrica Game 1 (seeds 20-29) and IDSSE matches 6-7 (4 halves). There it adds
**+0.113 [+0.090, +0.135]** and **+0.152 [+0.131, +0.175]** to the row above. It passes all 43 conditions
of its confirmation:
- the six scenarios of ball loss on both benches;
- the ball of the stoppages kept on the pitch;
- ten kinds of player noise, where it adds between +0.11 and +0.18.

After the bench took each pitch's own geometry, the same recipe was retrained and checked again
with new seeds. It passed the 43 conditions again: +0.129 [+0.104, +0.153] and +0.147 [+0.126, +0.170].
After the open-data speeds were fixed across player changes and halves, it passed them a third
time with other seeds: +0.132 [+0.109, +0.156] and +0.146 [+0.125, +0.168]. The submitted model is the
recipe retrained on the 10 matches after that fix, with training balls whose levels do not come from the
public ground truth: the selection picked the same recipe, and it passed the 43 conditions against
the control-radius pipeline on the reserve with new seeds (the lowest, +0.078 [+0.057, +0.103]). The second half is graded from frame 110,808 but kicks off at
113,742, so its first 2,934 graded frames are dead ball (the official FAQ); the pipeline labels every graded frame
before its half's kick-off D. The submitted file passed `validate_submission.py` and has `sha256`
`dab54052d5cfedf5a57fa60a7a4fb4d3c8884213e3888aa6a3ec78b58c400078` (H 52609, A 37034, D 69214, X 40462); four
machines produced it (Windows and macOS, Python 3.12 and 3.13).

With the first live-play model, the share of live frames labelled right rose from 0.88 to 0.93 on Metrica and
from 0.85 to 0.92 on IDSSE (against the change rule, on the matches kept aside).

**Tried and not adopted: short possessions weighing more.** True possessions shorter than 5 s are 9 in 10 of the
possessions the model misses on the open reserve (`explore/diagnose_changes.py`), and the metric counts every
possession alike. Counting their frames three times in training (weight 3, picked among 1, 3 and 5 on the selection
matches) also passed the 43 conditions against the control-radius pipeline. Against weight 1, in pairs on the same
balls and players of the reserve with new seeds, it is better in the default scenario
(+0.020 [+0.006, +0.035] on Metrica Game 1 and +0.011 [+0.003, +0.021] on IDSSE 6-7) but worse with 1.0 m of position
noise on both benches (-0.002 and -0.007): 41 of the 43 conditions. The rule fixed before that comparison admits a
change only if it wins all of them, so the submitted model counts every frame once. Its public-window score
(0.6526 [0.49, 0.78]) is within the noise and played no part in the decision.

## 6. Limitations

- **A trained model in the submission.** The possession model learns two providers' labels: Metrica's
  events and DFL's `BallPossession`. It is trained on simulated degradations of their tracking. If the
  organisers' labels or the real automatic tracking differ more than our simulations, the gain may be
  smaller. That is why it had to win on both benches and under every scenario and kind of player noise.
- **Who restarts.** The decoder does not use the team that restarts, and on top of the possession model it
  would not help: starting each live stretch with its true first team changes `spellF1` by -0.003 on Metrica
  and -0.002 on IDSSE (`explore/oracles_live.py`), because the model already gets who starts each stretch
  right. Before the model we trained one that names the restart team from the formation and the type of
  stoppage. On the IDSSE matches kept aside it names the team right in 91-100% of the cases, by
  type of stoppage, but the model as a whole did not pass the confirmation (+0.046 [+0.035, +0.057] on
  IDSSE, +0.009 [-0.004, +0.021] on Metrica, where it moves some stoppage ends the wrong way), so it is not
  in the submission.
- **The dead ball and the ball are what the model still misses most.** With the true dead ball, the
  possession model would gain +0.100 on Metrica and +0.075 on IDSSE, mostly at the edges of the stoppages
  (+0.071 and +0.052; first step of the physical edge rule, on the selection matches). With the full ball it would gain
  about 0.08 (first measurement of the live-play model). These ceilings are oracles measured on different versions of the
  model. None of the edge candidates changed the submitted file (section 1).
- **Change dating on the public window.** With the submitted model the median latency of the possession
  changes is -1 frame (mean +0.9; 90% of them within 18 frames), and the F1 of the changes at +/-25 frames is
  0.45 (10 of 20 matched, 24 predicted). With the earlier change rule the median was -12.5 frames (about
  0.5 s early) and that F1 was 0.29. It does not appear in the bench and rests on 20 changes of one
  five-minute window, so we do not read the difference as an effect.
- **The calibration data is not the organisers' ground truth.** Our possession labels come from event
  annotations, and the noise we add is a simulation of the automatic tracking. If the organisers' labels
  assign the owner with another radius or another rule, the best parameters may differ.
- **Small validation.** Seventeen possessions on the public window cannot separate versions.

With more time: Smart Tagging as a team signal, once it can be validated on another match; a decoder with
possession durations (semi-Markov), which could recover the short possessions the model still misses; and a
ball detector trained on external matches to fill the tracking gaps (with the full ball, the model would
gain about 0.08 more on both benches).

## 7. Reproduction

```bash
pip install -r requirements.txt      # Python 3.12 or 3.13; pinned versions
python possession.py /path/to/data   # the data dir holds tactical/BAR-ATH_tactical_*
                                     # (default: $MTAH_DATA) -> output/possession.csv,
                                     # and prints its sha256
```

Check the file with `evaluation/validate_submission.py` of the official repository. The submitted
file is `output/possession.csv` renamed to `Tiki_Data.csv`.

The file is the same byte for byte on any machine with these versions, as SUBMISSION.md and the
organisers' answer in issue #11 of the official repository require. The pipeline has no random step.
Its learned weights are committed in the repository: `live_model.json` and `stops_model.json`
(the identity model), both with integer thresholds and leaves. Retraining them needs
`requirements-train.txt` with `calibrate_live.py` and `calibrate_edges.py`, and is not needed to write the
CSV. The CSV is written with LF line endings on every OS, and the arithmetic that decides a label is
exact: integer signals, integer tree sums and an integer Viterbi. The nearest player is found by squared distance (IEEE multiply and
add, instead of the platform's `hypot`), the share of slow players is compared as integers, and
interpolation uses only IEEE operations. With a float moving average, which goes through BLAS, the
same machine wrote a different file on Metrica Sample Game 3 depending on the BLAS kernel (one frame
at 4 s / 0.3); with the integer count, every kernel tested gives the same file.

Seeds: none; nothing in the pipeline is random.

The open-data bench is reproduced with `python bench.py --compare v2 radio` (Metrica Sample Games in
`data/`) and `python explore/idsse_bench.py` (IDSSE, in `../idsse-data`). Every run is recorded in `docs/EXPERIMENTOS.md`.
