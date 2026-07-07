# Name
And Eff See (do you see?)

# Description
i was thinking of a cool challenge idea for finals but i got the wrong type of card :( and i locked it by accident!!!! help me please...
and i kinda want snacks :P

Note: this challenge requires a physical NFC card which can be loaned on request. Open a ticket and ping @suneshinefactory for the card!
If you require any NFC reading tools, do indicate in the ticket as well. Do note that you are strictly only allowed to READ the dump.

# Author
sunshinefactory

# Flag
`grey{0h_i_s33_y0u_4re_qu1te_g00d_at_th1s_nfc_th1n9_HuH}`

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
