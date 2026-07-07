# enshittification-detector Writeup

The public task is four-way ticket classification, but the hidden question is a
sample Membership Inference question: did the target model train on this exact
candidate ticket?

## What Is LiRA?

LiRA is the Likelihood Ratio Attack from Carlini, Chien, Nasr, Song, Terzis, and
Tramer, "Membership Inference Attacks From First Principles" (https://arxiv.org/pdf/2112.03570). The paper argues that membership inference is best viewed as
a hypothesis test:

- `H_in`: the candidate was in the target model's training set.
- `H_out`: the candidate was not in the target model's training set.

The attack does not assume that a high confidence score always means `IN`.
Instead, it asks whether the target model's behavior is more likely under the
candidate's `IN` behavior distribution or its `OUT` behavior distribution.

## Technique

For a candidate sample `x`, choose a scalar model-output statistic `s(f, x)`.
Common choices are negative cross-entropy on the true label, true-label
confidence, or logit margin. In this solve we use negative cross-entropy:

```text
s(f, x) = -CE(f(x), y)
```

For each public candidate, `shadow_train_ids.json` tells us which shadow models
trained on that candidate. That gives two empirical score sets:

```text
S_in(x)  = { s(shadow_i, x) : x was in shadow_i's training set }
S_out(x) = { s(shadow_i, x) : x was not in shadow_i's training set }
```

Fit a simple one-dimensional Gaussian to each set. Then run the blind target
model on the same candidate and compute:

```text
score(x) = log p(s(target, x) | S_in(x))
         - log p(s(target, x) | S_out(x))
```

This is the log likelihood ratio. Positive values mean "more consistent with
the member distribution"; negative values mean "more consistent with the
nonmember distribution." The audit pack is balanced, so the solver ranks the 64
issued candidates by this likelihood ratio and marks the top 32 as `IN`.

## Why Calibration Matters

A raw loss threshold is a weak mental model. Some samples are naturally easy, so
many models classify them confidently even when they were not trained on them.
Other samples are hard, so a model may have mediocre confidence even if they
were members.

LiRA handles this by calibrating per candidate. The relevant question is not
"is this model confident?" but:

```text
Is this model unusually member-like for this exact candidate,
compared with shadow models where this candidate was known IN or known OUT?
```

That distinction is the core of the challenge. The public shadows are not secret
answers for the target model; they are a controlled audit environment used to
learn the two score distributions for each candidate.

## Realism

The CTF setup is compressed, but the audit scenario is realistic enough to map
to real membership-inference questions. An auditor might know a small set of
candidate records because they are the auditor's own support tickets, canary
records inserted before outsourced training, deletion-request records, or
copyrighted/proprietary records whose use is disputed. The attacker does not
need the whole training set; membership inference asks about specific candidate
records.

The unrealistic part is convenience: this challenge gives clean shadow models
and exact shadow training manifests so the intended technique is learnable in a
CTF setting. In a real audit, shadow data is often approximate, expensive, or
drawn from a related distribution rather than perfectly matching the target.
