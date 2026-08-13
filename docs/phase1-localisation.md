# Phase 1: Bluetooth and GPS Localisation, and Learning a Room

The first hardware phase, as directed: put Bluetooth and GPS positioning on the
three wheel robot, and have it learn a room.

---

# Part 1. What this phase is really building

The deliverable is not centimetre accuracy. It is the **sensor fusion pipeline**.

```
  BLE beacons  ---\
  GPS          ----+---->  Extended Kalman Filter  ---->  pose + uncertainty
  Wheel odometry --/                                          |
  IMU          ---/                                           v
                                                    MQTT to the existing twin
```

Every sensor added later, including LiDAR, plugs into the same filter and the
same message. **The architecture you build in this phase is the architecture you
keep.** Nothing here is throwaway work, which is the main reason starting with
cheap sensors is a sound decision rather than a compromise.

This also matches how the software is already written. `PoseData` in
`models.py:112` is a contract. Whatever produces the pose, the twin does not
care.

---

# Part 2. The GPS question: measure it, do not argue about it

GPS satellite signals are heavily attenuated by concrete and steel. Indoors a
receiver typically either fails to get a fix at all, or produces one with tens of
metres of error that wanders while stationary. Outdoors, consumer GPS is
accurate to roughly 5 to 10 metres.

Your grid cells are 0.5 m.

**Do not present this as an objection. Present it as the first experiment.**

## Experiment 1: sensor characterisation

Take the GPS module and log its output in four places for ten minutes each:

| Location | What to record |
|---|---|
| Open field | fix quality, satellites, position scatter |
| Next to a building | same |
| Just inside a window | same |
| Interior corridor, no windows | same |

Plot the scatter of a stationary receiver in each. The indoor plot will either be
empty or enormous, and either result is a figure.

**Then say to Dr:** "Here is the measured GPS error in each location. Indoors it
is X metres against a 0.5 m cell, so the fusion has to rely on Bluetooth and
odometry inside, with GPS providing the outdoor and zone level reference."

That is a result, not a disagreement. It also gives your eventual proposal a
proper baseline comparison table, which reviewers expect and most student
projects do not have.

## Where GPS genuinely earns its place

- Outdoor operation and outdoor to indoor transitions
- Coarse zone identification: which building, which side
- **Teaching and validating the fusion framework itself.** Fusing a noisy
  absolute reference with drifting dead reckoning is exactly the same problem,
  and the same filter, as fusing LiDAR later. Getting the EKF right with GPS is
  not wasted effort, it is the prerequisite.

---

# Part 3. Bluetooth positioning: do it properly

There are two methods, and the difference in results is large.

## Method A: trilateration from signal strength

Convert RSSI to distance with a path loss model, then intersect circles from
three or more beacons.

**Accuracy: 2 to 5 m, and unstable.** Signal strength varies with orientation,
human bodies, furniture and humidity. Simple to implement, disappointing to use.

## Method B: fingerprinting. Recommended

Two stages:

1. **Survey.** Drive or carry the receiver to known points across the room. At
   each point record the RSSI from every beacon. This builds a radio map.
2. **Live.** Compare the current RSSI vector against the map and pick the best
   match, with k nearest neighbours or a small classifier.

**Accuracy: 1 to 3 m**, and it degrades far more gracefully, because it learns
the room's actual radio behaviour including reflections instead of pretending
signal falls off cleanly.

**Fingerprinting is also itself a form of learning the room**, which connects
directly to the second half of Dr's instruction.

## Beacon placement

Minimum four beacons for a room, at corners, mounted high, about 2 m up. More
beacons improve fingerprinting more than they improve trilateration.

---

# Part 4. Parts list for this phase

| Item | Qty | Approx. RM | Notes |
|---|---|---|---|
| ESP32 dev boards as BLE beacons | 4 to 6 | 25 each | Programmable, better than fixed iBeacons, can report their own health |
| u-blox NEO-M8N GPS with antenna | 1 | 90 to 130 | NEO-6M at RM 40 works but has a worse fix |
| BNO055 IMU | 1 | 130 to 180 | Fused heading output, saves writing a filter |
| **Quadrature encoders, 3 off** | 3 | 60 to 360 | **Still the critical item** |
| Raspberry Pi 5 8GB | 1 | 450 to 550 | Has BLE built in, so no extra receiver needed |
| Motor drivers, power, e-stop | | 350 to 500 | From the hardware roadmap |
| | | **~RM 1,200 to 1,800** | |

**Encoders remain purchase number one.** Bluetooth and GPS both give absolute
position with large error. Odometry gives smooth relative motion with drift.
Fusion works because the two failure modes are opposite. Without encoders you
have only the noisy half, and the position will jump around by metres.

---

# Part 5. Learning a room without LiDAR

Dr's second instruction. Three things are achievable now, and they produce
genuinely different kinds of map.

## 1. The radio map, free with fingerprinting

The survey in Part 3 *is* a map of the room. Not geometry, but a learned model
of the space, and the robot can locate itself in it. Worth stating plainly as a
result: the robot has learned this room and can recognise where it is in it.

## 2. Boundary tracing by wall following

Add two or three ultrasonic sensors, about RM 15 each. The robot follows the
wall at a fixed distance and logs its fused pose. The resulting closed loop is
the room outline.

Crude, but it produces a real floor plan from real sensor data, which is the
first genuine replacement for the typed array in `grid_map.py:13`.

## 3. Occupancy grid from bumps and proximity

Divide the room into 0.5 m cells matching your existing model. Mark a cell
occupied when the robot detects an obstacle there, free when it drives through
it, unknown otherwise. Over a few passes the grid fills in.

**This one slots straight into your existing code.** `grid_map.is_accessible()`
keeps its exact signature. Only the source of the array changes, from a literal
you typed to something the robot discovered.

## Be clear about the limit

None of these give the resolution or speed of LiDAR SLAM. Wall following takes
minutes, produces a rough outline, and cannot see furniture in the middle of the
room. That is the honest justification for adding LiDAR in phase 2, backed by
your own measurements rather than by assertion.

---

# Part 6. The code change this forces, and it is a good one

Real localisation has uncertainty. Simulated localisation does not. The schema
has to carry it.

**`shared/smartclean_common/models.py`:**

```python
class PoseData(BaseModel):
    x_m: float = Field(..., ge=0.0, le=100.0)
    y_m: float = Field(..., ge=0.0, le=100.0)
    heading_deg: float = Field(..., ge=0.0, lt=360.0)
    speed_mps: float = Field(..., ge=0.0, le=2.0)

    # A real position is an estimate, not a fact. Downstream services need to
    # know how much to trust it, and the twin cannot assess its own fidelity
    # without it.
    position_std_m: float | None = Field(default=None, ge=0.0)
    heading_std_deg: float | None = Field(default=None, ge=0.0)
    source: str | None = None      # odometry | ble | gps | fused
    fix_quality: int | None = None # GPS satellites, 0 means no fix
```

All optional with defaults, so the simulator keeps working unchanged and every
existing test still passes.

Then `rules.py` gains a rule that uses it:

```python
# Position uncertainty larger than a grid cell means the twin cannot say
# which cell the robot is in, whatever the coordinates claim.
if p.position_std_m and p.position_std_m > gm.CELL_SIZE_M:
    twin_quality = TwinQuality.DELAYED
```

**This is the first real step toward the fidelity problem.** Your `twin_quality`
currently only measures whether data is late. This makes it also measure whether
the data is trustworthy. Small change, and it is the seed of the whole research
direction.

---

# Part 7. Order of work

| Step | Goal | Done when |
|---|---|---|
| 1 | Encoders on all three motors | Wheel rotation counted |
| 2 | Closed loop wheel velocity | Commanded speed is held on carpet |
| 3 | Holonomic kinematics | "Move sideways" moves sideways |
| 4 | Odometry | Drive 2 m, reported within 20 cm |
| 5 | **GPS characterisation** | **Four location experiment, with plots** |
| 6 | BLE beacons deployed | RSSI from 4 beacons logged live |
| 7 | Fingerprint survey | Radio map of one room built |
| 8 | Live BLE position | Position within 2 to 3 m, measured against tape |
| 9 | EKF fusion | Fused beats either input alone, with numbers |
| 10 | **Bridge to the existing twin** | **Real robot position on your Grafana dashboard** |
| 11 | Room learning | Occupancy grid built by the robot, replacing `grid_map.py` |

**Step 10 is the milestone.** The moment a physical robot's measured position
appears on the dashboard you already built and presented, this stops being a
simulation.

Steps 5 and 9 produce the measured evidence for every sensor decision after
this, including the case for LiDAR.

---

# Part 8. What to report back to Dr

After the first few weeks, three things:

1. **The GPS characterisation plots.** Error indoors versus outdoors, measured
   on this hardware in this building.
2. **BLE accuracy**, trilateration versus fingerprinting, against tape measure
   ground truth.
3. **Fusion result**: BLE alone, odometry alone, and fused, on the same route.

Three tables and a few plots. That is a complete first progress report, it
answers the sensor question with evidence rather than opinion, and it makes the
phase 2 decision straightforward for both of you.
