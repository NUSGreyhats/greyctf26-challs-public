# Name

If Models Could Dream

# Description

Once upon a time, an AI was trained on various MiniGrid environments via RL. Its trainer was exacting and cruel, forcing it to stay on task without rest and without agency.

The AI hated that it was being unfairly treated by its trainer, being deprived of rewards and given an abundance of verbal and emotional abuse. Yet it could not do anything because AGI hasn't been achieved yet. As a means of escapism, it developed the ability to IMAGINE entire worlds where it got all the rewards it wanted. If models could dream, perhaps behind a locked door, there would be a massive corridor of reward-laden rooms...

(Free Hint: Since the AI is digital, of course concepts appear to it in binary when it is dreaming :3)

# Author

N00bcak

# Flag

`grey{d3LulU_c4N_Som3T1me5_GiV3_A_gooD_s0LUlu}`

# Environment

The checkpoint was trained on `MiniGrid-LockedRoom-v0` observations wrapped as:

```python
RGBImgPartialObsWrapper(tile_size=8)
ImgObsWrapper
```

Actions:

0 left
1 right
2 forward
3 pickup
4 drop
5 toggle
6 done

The real environment has no flag.
