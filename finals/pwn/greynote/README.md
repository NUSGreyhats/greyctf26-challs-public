# Name

greynote

# Description

Just a really normal pwn challenge, nothing special... Right?

# Author

elijah5399

# Flag

`grey{i sure hope you didn't cheese that challenge somehow U_U}`

# Deployment

Use the Compose file for local deployment with bounded QEMU concurrency:

```sh
docker compose up --build
```

The default deployment assumes no KVM or nested virtualization support. QEMU
will run without mounting `/dev/kvm`. If a future host explicitly supports KVM,
infra can add a local override to mount `/dev/kvm`, but the checked-in
deployment does not depend on it.
