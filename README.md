# Comms

Comms is a container wrapper around
[EMANE](https://github.com/adjacentlink/EMANE) designed to provide simple and
adaptable emulated network layer interference.

The Comms containers extracts away the specialized configuration that EMANE
needs to perform its capabilities into plug and play, easy to use virtual IPs.

## Usage

1. Start by building the container from source or pulling the [prebuilt
   container hosted in the GitHub
   registry](https://github.com/Tetrago/comms/pkgs/container/comms).

    - From there, start the container with `--help` to get an idea of what Comms is capable of.

2. To create a simple virtual network, we'll need a container bridge network to start with:

    ```sh
    podman network create my-test-network
    ```

> [!NOTE]
> It's your choice whether you want to use `podman` or `docker`; Comms works with both!

3. Then, we'll create two Comms containers. Each container will provide a
   virtual `emane0` interface with their assigned virtual IP:

    ```sh
    podman run --rm -dit --name alice --network my-test-network comms --host-if eth0 --address 10.0.0.1
    podman run --rm -dit --name bob --network my-test-network comms --host-if eth0 --address 10.0.0.2
    ```

> [!NOTE]
> Be sure to run with `--help` to get an idea of what Comms can do.

> [!WARNING]
> You might need to add some flags to get Comms to work correctly on your
> runtime:
>
>   - `--privileged`
>   - `--user 0`
>   - `--device /dev/net/tun`
>   - `--cap-add NET_ADMIN`

> [!TIP]
> `eth0` is the default interface name used by both podman and docker, but
> you can add `:interface_name=myif0` after your network name if you need
> to change it to something else or specify it explicitly.

4. Now that we've got two containers running, we can open a shell on one of
   them to see our virtual address in action:

   ```sh
   podman exec -it alice bash
   $ ip a
   ```

   You should see something along the lines of:

   ```sh
   emane0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UNKNOWN group default qlen 1000
    link/ether 02:02:00:00:00:01 brd ff:ff:ff:ff:ff:ff
    inet 10.0.0.1/24 brd 10.0.0.255 scope global emane0
       valid_lft forever preferred_lft forever
    inet6 fe80::2:ff:fe00:1/64 scope link
       valid_lft forever preferred_lft forever
   ```

    Congrats! You've made a virtual network.

5. However, you might have noticed that you can't ping Bob (`10.0.0.2`) from Alice (`10.0.0.1`).

    This is expected. While both Alice and Bob are connected to the same EMANE
    network, by design they will not be able to talk to eachother until we open
    the links between them. Comms is designed this way to support more complex
    network topologies than just dense networks.

    To allow Alice and Bob to communicate, we'll need to create rules to open
    their link; two rules, specifically, as links are one way.

    First, allow traffic from Bob to Alice:

    ```sh
    podman attach alice
    [10.0.0.1]~> set 2 latency=0
    [10.0.0.1]~> # make sure to detach (Ctrl + P, Ctrl + Q) to avoid killing the container
    ```

    There is no explicit "enable" rule, we just need *some* rule to open the
    link. `loss=0` also would have worked here. To see what rules you can set,
    type `set ?`. To see all available commands, simply type `help`.

    Then, allow traffic from Alice to Bob:

    ```sh
    podman attach bob
    [10.0.0.2]~> set 1 latency=0
    ```

    While we're in here, we can ping Alice directly:

    ```sh
    [10.0.0.2]~> shell
    $ ping 10.0.0.1
    PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.
    64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.035 ms
    64 bytes from 10.0.0.1: icmp_seq=2 ttl=64 time=0.043 ms
    64 bytes from 10.0.0.1: icmp_seq=3 ttl=64 time=0.042 ms
    ```

    Congrats! You're talking over a virtual network.

    Feel free to play around by adding different network effects using the
    `set` command to see what Comms can do.

## Examples

Check out the compose files in the examples directory to try some different
network topologies supported by Comms:

```sh
podman compose -f examples/simple.yml up -d
```
