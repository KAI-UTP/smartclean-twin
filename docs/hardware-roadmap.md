# From Simulation to a Real Robot

A plan for turning SmartClean Twin into a physical system, starting from a
three wheel chassis whose motors turn and nothing else.

Prices are approximate and in Malaysian Ringgit. Check current prices before
ordering. Cytron is in Penang, so local sourcing avoids import delays.

---

# Part 1. The six layers, and where the FPGA belongs

The single most useful thing to understand is that a robot is a stack, and each
layer has a different job with a different timing requirement. Most projects
fail because they mix layers.

| Layer | Job | Timing | Status |
|---|---|---|---|
| **0. Chassis and motors** | Physically move | mechanical | **You have this** |
| **1. Power and drivers** | Deliver current to motors | continuous | Need |
| **2. Real time control** | Hold commanded wheel speed | **1 ms, hard deadline** | Need. **FPGA goes here** |
| **3. Sensing** | Position, orientation, room | 10 to 100 ms | Need |
| **4. Onboard computer** | SLAM, ROS 2, MQTT bridge | 100 ms, soft | Need |
| **5. The Digital Twin** | State, AI, dashboards, console | 1 s | **You have this, unchanged** |

## Where the FPGA fits, and where it does not

**Layer 2, and only layer 2.**

An FPGA is good at things that must happen at an exact moment, every time,
forever. That describes motor control precisely:

- Generating PWM waveforms for the motors
- Decoding quadrature encoder pulses, which can arrive tens of thousands of
  times per second
- Running the PID loop that holds a commanded wheel speed
- Emergency stop that cannot be delayed by an operating system

An FPGA is a **poor choice** for layers 4 and 5. SLAM, ROS 2, MQTT, the Python
services and the AI models all want a general purpose CPU with an operating
system and libraries. Implementing those in hardware would take years and be
worse.

### Be honest about this in your proposal

A microcontroller such as an STM32 handles layer 2 perfectly well and costs
RM 30. If you use an FPGA purely because it is available, a reviewer will ask
why, and "it was there" is not an answer.

There are two defensible reasons, and both are genuine research angles:

1. **Deterministic latency as a twin property.** A twin's accuracy depends on
   knowing exactly when a measurement was taken. An FPGA can timestamp encoder
   and IMU samples with nanosecond precision and no operating system jitter. On
   a Linux board that jitter is hundreds of microseconds and variable. You can
   *measure* this, and measured timing determinism feeding twin fidelity is a
   publishable contribution.

2. **Hardware acceleration of perception.** LiDAR scan matching and sensor
   fusion parallelise well. Doing them in fabric frees the CPU and cuts latency.

If you use one of those framings, the FPGA becomes an architectural decision
rather than a component you were given.

### The board that makes this elegant

Do not buy a plain FPGA board such as a Basys 3. It has fabric but no processor,
so you would still need a separate computer for layer 4.

Buy a **Zynq** instead. A Zynq chip has ARM CPU cores and FPGA fabric on the
same die, connected by a fast internal bus. One board covers layers 2 and 4:

| Board | Approx. price | Notes |
|---|---|---|
| **AMD Kria KR260** | RM 2,000 to 2,600 | Marketed as a robotics starter kit, runs Ubuntu and ROS 2 out of the box. The lowest risk option. |
| **PYNQ-Z2** | RM 1,000 to 1,400 | Cheaper, Python tooling, smaller fabric. Good if the budget is tight. |
| Raspberry Pi 5 + STM32 | RM 500 to 600 | No FPGA. The sensible engineering answer if the FPGA is dropped. |

**Architecture with a Zynq:**

```
   FPGA fabric                     ARM cores (Linux)
   ---------------                 ------------------
   PWM generation                  ROS 2 nodes
   Encoder decoding      <----->   SLAM
   PID velocity loop     AXI bus   MQTT bridge  ---> your existing twin
   Emergency stop                  Ubuntu
```

Ask Dr which Zynq boards UTP already owns before buying anything. Many
electrical engineering departments have Zybo or PYNQ boards in a cupboard.

---

# Part 2. What to buy

## The chassis: three omni wheels, holonomic

The rollers around each wheel rim identify these as omni wheels. Three of them,
all driven, spaced 120 degrees apart. This is a **holonomic** or **kiwi drive**
platform, not differential drive.

Holonomic means the robot can translate in any direction without turning first.
It can strafe sideways, and it can rotate on the spot while moving.

### The good news, and it is genuinely good

**Your existing eight direction control model is a natural fit.** Look at
`MANUAL_MOVES` in `simulator.py:48`. You already treat movement as eight
directions each with a heading. On a differential robot, moving up and left
means turn, then drive, then turn back, and your simulated model would have been
a lie. A holonomic robot really can move diagonally in one motion. The control
abstraction you wrote for the simulator is closer to this hardware than it would
have been to a normal two wheel robot.

The same applies to the cleaning path. A holonomic robot can follow the
lawnmower pattern in `grid_map.py:52` without the turning overhead at the end of
each row.

### The bad news, and you must plan for it

**Omni wheel odometry is significantly worse than differential drive odometry.**
The rollers are designed to slip sideways, which is what makes the robot
holonomic, and that same slip means wheel rotation does not map cleanly to
distance travelled. Dead reckoning drifts faster and less predictably.

Three consequences:

1. **The LiDAR is not optional.** On a differential robot you can get useful
   odometry without it. Here you cannot. Budget for it from the start.
2. **The IMU matters more.** Heading from encoders alone will be poor.
3. **Three motors, three encoders, three PID loops**, not two of each. Costs and
   wiring go up by half.

### Confirm before ordering

- Are the three wheels really at 120 degrees, or is it two plus one?
- Do the motors have encoders? On a toy style platform they usually do not, and
  fitting them is purchase number one.
- Is this the actual robot Dr has, or a reference photo of a similar one?

## Phase 1: make it drive on command, roughly RM 400

The goal is closed loop velocity control. You send "0.2 m/s" and it goes
0.2 m/s, uphill or on carpet.

Three wheels means three of everything.

| Item | Qty | Approx. price | Why |
|---|---|---|---|
| Cytron MDD10A dual driver | 2 | RM 90 each | 4 channels, you need 3 |
| **Quadrature encoders** | 3 | RM 60 to 120 total | **The critical item.** No feedback without them |
| 12 V battery pack with BMS | 1 | RM 150 to 300 | LiPo 3S or Li-ion 4S |
| Buck converter, 12 V to 5 V | 1 | RM 25 | Logic at 5 V, motors at 12 V |
| Emergency stop button | 1 | RM 20 | Non negotiable on anything that moves |

**If the motors have no encoders, that is the first problem to solve.** Either
fit them, or replace the motors with Cytron SPG30E geared motors which include
them, roughly RM 120 each, so RM 360 for three. A robot without encoders cannot
know how far it has travelled, and every layer above collapses.

### The extra piece holonomic needs: inverse kinematics

A differential robot takes two wheel speeds. A holonomic robot takes a velocity
vector and a rotation, then computes three wheel speeds from them. For three
wheels at 120 degrees:

```
v1 = -sin(0)   * vx + cos(0)   * vy + R * omega
v2 = -sin(120) * vx + cos(120) * vy + R * omega
v3 = -sin(240) * vx + cos(240) * vy + R * omega
```

where `R` is the distance from the robot centre to each wheel. This runs on
every control cycle, before the three PID loops.

**This is where the FPGA argument becomes genuinely strong.** On a
microcontroller the three PID loops run one after another, so wheel three is
always updated slightly later than wheel one. In FPGA fabric all three run at
the same instant, in parallel, along with the kinematics. For a holonomic
platform, where the three wheels must act as one coordinated system, simultaneous
update is not a luxury argument. That is a defensible reason to choose an FPGA
that has nothing to do with the board being available, and it is measurable:
compare tracking error between sequential and parallel control at the same
loop rate.

## Phase 2: know where it is, roughly RM 200

| Item | Approx. price | Fills which telemetry field |
|---|---|---|
| BNO055 IMU | RM 130 to 180 | `heading_deg` |
| INA219 current sensor | RM 20 | `battery_a`, `motor_current_a` |
| DS18B20 temperature sensor | RM 15 | `motor_temperature_c` |

The BNO055 is worth the extra over an MPU6050 because it fuses internally and
outputs a stable heading, saving you a filter you would otherwise have to write.

Encoders plus IMU gives odometry: adequate for tens of seconds, then it drifts.
Fixing that drift is what phase 3 is for.

## Phase 3: see the actual room, roughly RM 500. Not optional here

| Item | Approx. price | Why |
|---|---|---|
| **RPLidar A1M8** | RM 450 to 550 | 360 degree scan, 12 m range, the standard 2D SLAM sensor |

This is the item that answers Dr's point about reading the real room rather than
a hardcoded array. With this plus SLAM, the robot builds its own map.

On a differential robot this could be deferred. On omni wheels it cannot,
because the odometry drift has to be corrected by something that observes the
world directly.

## Phase 4: the computer, RM 400 to 2,600

Either a Raspberry Pi 5 8GB at roughly RM 450, or the Zynq board discussed
above if the FPGA route is taken.

## Not now

**Do not buy a dirt sensor.** Your telemetry has a `dirt_score` field, but there
is no cheap sensor for it. Options are a downward camera with a trained
classifier, which is a project in itself, or vacuum motor current as a proxy,
which is crude. Leave the field unpopulated at first and be explicit that it is
unpopulated. An honest gap is better than a fabricated number, and in a Digital
Twin a fabricated number is a correctness bug.

## Totals

| Route | Approx. total |
|---|---|
| Minimum: drives and reports to the twin, no SLAM | RM 1,200 to 1,600 |
| **Recommended: adds LiDAR and SLAM** | RM 1,800 to 2,500 |
| With Kria KR260 for the FPGA research angle | RM 3,400 to 4,500 |
| Add RM 360 if the motors need replacing for encoder versions | |

---

# Part 3. Software migration, file by file

The important claim, and it is true: **no service imports the simulator.** Every
service subscribes to an MQTT topic. So a physical robot publishing the same
schema needs changes to zero of them.

## What is genuinely new: one service

**`services/robot-bridge/`**, a ROS 2 node running on the robot.

```
ROS 2 topics                    SmartClean MQTT topics
------------                    ----------------------
/odom          -->  bridge -->  smartclean/SCR01/telemetry/raw
/scan          -->              (16 field schema, unchanged)
/imu
/battery_state

/cmd_vel       <--  bridge <--  smartclean/SCR01/command/motion
                                smartclean/SCR01/ack
```

It translates between the two worlds and does nothing else. Perhaps 300 lines.
The rest of the system does not know it exists.

## What changes, and how much

### `grid_map.py`: the biggest conceptual change, small code change

Today `_LAYOUT` at line 13 is an array you typed. It becomes an occupancy grid
published by SLAM.

**Keep the function signatures identical.** `is_accessible(row, col)` still takes
a row and a column and still returns a bool. Only the source of truth changes,
from a literal to a live map. Everything that calls it is unaffected.

```python
# before: a fixed array
_LAYOUT = np.array([[1,1,1,...], ...])

# after: the latest occupancy grid from SLAM, same interface
def is_accessible(row, col) -> bool:
    return _occupancy[row, col] < OCCUPIED_THRESHOLD
```

### `simulator.py`: promoted, not deleted

**This is the idea to build the research proposal around.**

Today the simulator pretends to be the robot. In the real system it runs
alongside the real robot, faster than real time, predicting what will happen
before the robot commits to it. Your `/whatif` endpoint already does exactly
this, pointed at a simulated asset instead of a physical one.

The difference between what the simulator predicts and what the real robot then
does is the **sim to real gap**. Measuring it, and reducing it by tuning the
simulator against real logs, is a genuine research contribution and it is the
natural next step from what you have already built.

### `models.py`: pose gains uncertainty

A simulated position is exact. A real one is an estimate with error. The schema
needs to carry that:

```python
class PoseData(BaseModel):
    x_m: float
    y_m: float
    heading_deg: float
    speed_mps: float
    covariance: list[float] | None = None   # new, from the localiser
    source: Literal["odometry", "slam", "fused"] = "fused"   # new
```

Some sensor fields also become optional, because a real robot may not have every
sensor from day one. `SensorData` already defaults `water_level_pct`, so the
pattern is established.

### `rules.py`: thresholds become learned

Today: `if s.motor_temperature_c > 70.0`. A hardcoded constant.

Real motors differ from each other and drift as they age. Learn a per robot
baseline the same way `anomaly_detector` already learns one. This is a
limitation you already identified and told Dr about, which is exactly why
volunteering it was worth doing: it is now a roadmap item rather than a
weakness.

### `state-engine/main.py`: the single robot assumption

Lines 44 to 46 keep coverage and sequence in module globals. Key them by
`robot_id` in a dictionary. The topic hierarchy at `topics.py:7` already
anticipates a fleet.

### Unchanged entirely

`telemetry-ingestion`, `ai-service`, `command-api`, `web-control`, Grafana,
InfluxDB, CI. Your validation gate becomes **more** valuable, not less: real
sensors produce genuine dropouts, spikes and NaNs, which is exactly what
`main.py:119` exists to catch.

## One upgrade worth knowing

You are already using Omniverse. **NVIDIA Isaac Sim** is the robotics build of
the same platform, with a native ROS 2 bridge and support for training in
simulation before deploying to hardware. Moving from Omniverse Kit to Isaac Sim
is a natural step and keeps your existing USD scene work.

---

# Part 4. Order of work

Each phase produces something demonstrable. Do not skip ahead: every phase
depends on the one before it.

| Phase | Goal | Done when |
|---|---|---|
| **1** | Fit encoders to all three motors | Each wheel's rotation can be counted |
| **2** | Closed loop velocity per wheel | Each wheel holds its commanded speed on carpet |
| **3** | Holonomic kinematics | Commanded "0.2 m/s sideways" moves sideways, not in an arc |
| **4** | Odometry | Drive 2 m, reported distance within 20 cm. Expect worse than differential drive |
| **5** | ROS 2 on the computer | `/odom` and `/cmd_vel` work, with `linear.y` actually used |
| **6** | **Bridge to the existing twin** | **The real robot appears in your Grafana dashboard** |
| **7** | Command path | A console button moves the physical robot |
| **8** | LiDAR and SLAM | The robot builds a map of a real room |
| **9** | Replace `grid_map.py` | Navigation uses the discovered map |
| **10** | Measure the sim to real gap | Numbers comparing prediction to reality |

Phase 3 is new compared with a differential robot, and phase 4 will be harder
than you expect. Do not treat drifting odometry as a bug; it is a property of
omni wheels and the reason phase 8 exists.

**Phase 5 is the milestone that matters.** The moment a physical robot's real
position appears on the dashboard you already built, the project stops being a
simulation with ambitions and becomes a Digital Twin of a physical asset.

Everything from phase 6 onward is research. Phases 1 to 5 are engineering, and
they are the part most likely to take longer than expected.

---

# Part 5. Questions to settle with Dr

1. **Do the three motors have encoders?** If not, that is purchase number one and
   nothing else can start.
2. **Are the wheels at 120 degrees?** Confirm the geometry, because the inverse
   kinematics depends on the exact angles and the wheel radius.
3. **Which FPGA boards does UTP already own?** A Zynq in a cupboard changes the
   plan and the budget.
4. **Is the FPGA a requirement or a suggestion?** For a three wheel holonomic
   platform it is defensible, because the three control loops genuinely benefit
   from running in parallel. It remains the wrong tool for SLAM and for the twin
   services, and saying so clearly will earn more credibility than agreeing to
   use it everywhere.
5. **Is the target a working robot, or a measured result?** A demo and a paper
   need different amounts of polish and different amounts of measurement.
