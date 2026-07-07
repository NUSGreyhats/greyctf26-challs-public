# n00bcaks_last_gradient Writeup

The public files leak enough information to reconstruct the private training
sample. We are given the model definition, the trained weights, and a gradient
dump from one cross-entropy training step. That gradient is not just metadata:
for a single sample, it strongly constrains both the label and the input image.

## What Leaked

The distributed `gradients.pt` payload contains:

- input shape `1x1x64x64`
- `10` output classes
- `cross_entropy` as the loss
- `8` gradient tensors, one for each parameter tensor in the public CNN

Together with `model.py` and `model_weights.pt`, this gives the attacker
everything needed to replay a training step on candidate inputs and compare the
resulting parameter gradients against the leaked ones.

## Vulnerability

Gradients from one training example can reveal the example itself. If the model
weights are known, an attacker can search for an input `x` and label `y` whose
loss gradient matches the leaked gradient:

```text
grad_theta(CE(model(x), y)) ~= leaked_grad
```

This is a gradient inversion attack. The challenge makes the leakage especially
direct because the dump comes from a single image rather than an averaged batch.
The target image is also small, grayscale, and passed through a compact CNN, so
optimizing directly over the pixels is practical.

## Label Recovery

The label can be recovered before reconstructing the image. For a final linear
layer trained with cross-entropy, the bias gradient is:

```text
softmax(logits) - one_hot(y)
```

All non-target classes have positive entries, while the true class has the one
large negative entry. In the public gradient dump, the final bias gradient's
minimum is at index `7`, so the solver uses class `7`.

## Gradient Matching Solve

`solution.py` freezes the public model and optimizes a dummy image instead of
the model weights. The dummy image is represented as unconstrained logits and
passed through `sigmoid`, keeping the candidate pixels in `[0, 1]`.

For each optimization step:

1. Run the public model on the current candidate image.
2. Compute cross-entropy against the recovered label.
3. Use `torch.autograd.grad(..., create_graph=True)` to compute the candidate
   parameter gradients.
4. Minimize the summed MSE between candidate gradients and leaked gradients.
5. Let Adam update only the image logits.

`create_graph=True` matters because the gradient-matching objective must itself
backpropagate through the computed candidate gradients. Without it, the solver
could measure the mismatch but could not use that mismatch to update the image.

## Denoising

The raw gradient-matching objective is enough to recover the signal, but it can
leave noisy pixels. The solve adds a small total-variation penalty:

```text
objective = gradient_mse + tv_weight * total_variation(candidate)
```

This encourages neighboring pixels to be similar, which makes the reconstructed
stamp and text easier to read without changing the core attack.

## Result

After a few thousand Adam steps, the reconstructed `64x64` image visibly reveals
the flag text. The solve saves intermediate progress images and the final output
as `final_reconstruction.png` in the selected reconstruction directory.
