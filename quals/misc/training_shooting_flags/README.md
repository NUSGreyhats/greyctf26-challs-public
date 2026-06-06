# Name
Training Shooting Flags

# Description
After our GreyArmy's Shooting Formation got discovered, it's back to basics. 
This time, our commanding officer is deadset on making sure our formation is right before revealing any part of it.
We are in full training mode!

Hint: knowledge on GreyMecha/Army will help. You don't need the board to solve the challenge

# Author
hackin7

# Flag
`grey{lmao_imagine_revvin}`

<!--
CTFd Whale is used for per-team/per-user instancing. Keep it disabled for normal CTFd challenges.

Currently, we only support HTTP Whale challenges. Direct nc challenges are not recommended with Whale because users
can scan ports to find other teams' instances.

To enable Whale for HTTP challenges:
- set enabled to true.
- redirect_port is the port the service listens on inside the container.
- the Docker Compose service must declare a local image tag with image: so CTFd Whale can run the built image.
- memory_limit and cpu_limit are the defaults. Only change them if needed, and keep them low because resources are shared.

NOTE: The entire `# Whale` block can be omitted if you do not need it.
-->

# Whale
enabled: false
redirect_port: 8000
memory_limit: 64m
cpu_limit: 0.1
