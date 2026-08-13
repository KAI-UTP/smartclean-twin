# Research Direction: Vision, Semantics and Self Building Twins

Where the project goes after the robot drives: giving it sight, giving the map
meaning, and letting the twin build itself.

This is a multi year vision. The staging at the end matters as much as the ideas.

---

# Part 1. The three technologies, and which you actually need

These get used interchangeably in conversation, but they are different things
with very different maturity and cost.

## VLM: Vision Language Model

**Images in, text out.** You show it a photo and ask a question.

> "Is this floor dirty?"
> "What objects are in this room?"
> "Is this surface carpet or tile?"

Examples: Qwen2-VL, LLaVA, Gemini, GPT-4V.

**Maturity: high.** These work today and are the practical starting point.

## VLA: Vision Language Action

**Images and an instruction in, robot commands out.** The model directly outputs
motion rather than text.

Examples: OpenVLA, RT-2, Octo.

**Maturity: low for your case.** Almost all VLA work targets robot arms doing
manipulation, trained on datasets of grasping and placing. There is far less for
mobile floor robots, and none of it is a drop in solution. Treat VLA as year
three, not year one, and say so in a proposal rather than implying it is ready.

## Semantic SLAM: geometry plus meaning

**This is the one that matters most for you, and it is the honest centre of the
idea.**

Plain SLAM answers *where are the walls*. It gives you an occupancy grid: a
better version of the `1 0 1 0` array in `grid_map.py`, discovered rather than
typed. It still does not know what anything **is**.

Semantic SLAM adds a VLM or object detector on top, so the map becomes labelled:

| Plain SLAM says | Semantic SLAM says |
|---|---|
| cell (4,7) is occupied | cell (4,7) is a **desk leg** |
| cell (2,3) is free | cell (2,3) is **carpet**, currently **dirty** |
| cell (8,1) is occupied | cell (8,1) is a **charging dock** |

Relevant open work: ConceptGraphs and OK-Robot build open vocabulary 3D scene
graphs from camera data plus a VLM. Read these before writing a proposal, since
they define the current baseline you would be measured against.

---

# Part 2. Why this fits your existing architecture with no rewrite

**A VLM does not need to run on the robot.**

Your system is already publish and subscribe. Adding vision is a tenth service
that subscribes to a topic, exactly like `ai-service` does today:

```
Robot camera
   |  publishes frames
   v
smartclean/SCR01/camera/frame          <- new topic
   |
   v
services/vision-service/               <- new service, runs on a workstation
   VLM: what is this? is it dirty?
   |
   v
smartclean/SCR01/semantic              <- new topic
   |
   +--> state-engine     (dirt level now comes from vision)
   +--> InfluxDB         (measurement: robot_semantic)
   +--> Grafana, Omniverse, console
```

**Changes required to the six existing services: zero.** They subscribe to
topics. A new publisher appears and the ones that care subscribe to it.

This is the payoff from validating at the boundary and defining the contract in
one file, and it is worth stating explicitly in any proposal: the architecture
was designed so that capability can be added without disturbing what works.

## The two speed structure this creates

| Tier | Runs on | Rate | Job |
|---|---|---|---|
| Reflex | FPGA | 1 ms | Motor control, emergency stop |
| Navigation | Onboard SBC | 100 ms | SLAM, obstacle avoidance |
| **Semantic** | **Workstation** | **1 to 5 s** | **VLM: what is this, is it dirty** |
| Twin | Existing services | 1 s | State, prediction, dashboards |

A VLM taking two seconds to answer "that is a carpet stain" is fine. A motor
control loop taking two seconds kills the robot. Keeping these tiers separate is
the correct architecture, and being able to justify why is worth more in a viva
than making everything fast.

---

# Part 3. The immediate win: `dirt_score`

**Your telemetry schema has a field you have no sensor for.**

`models.py:126` defines `dirt_score`. In simulation it comes from
`grid_map.generate_dirt_map()`, which is a random number generator. In my earlier
hardware notes I said to leave it unpopulated, because there is no cheap dirt
sensor you can buy.

**A camera plus a VLM is that sensor.**

```
Camera frame ->  VLM  ->  "the floor in this image shows scattered
                           crumbs and a liquid stain, roughly 30 percent
                           of the visible area"
                       ->  dirt_score: 0.62
                       ->  surface: carpet
```

This is the strongest short term result in the whole vision direction, because:

1. It fills a real gap in a schema you already defined and defended.
2. It is measurable. Photograph 100 floor patches, have humans rate them, compare
   against the VLM. That is a results table.
3. It changes robot behaviour, not just the dashboard. Dirty area detected leads
   to slower pass, brush on, revisit. Your `CleaningState.REPEAT_REQUIRED` in
   `models.py:48` already exists and is currently driven by a random number. It
   would become driven by something real.

If you do one vision thing first, do this.

---

# Part 4. The twin that builds itself

This is Dr's point about building the 3D model from what the robot sees, and it
is the most publishable part.

## Where you are now

`omniverse/create_scene.py` is 254 lines of hand written geometry. You typed the
room dimensions, placed three desks by hand, and laid out 100 tiles in a loop.
The virtual model was authored by a human.

## Where this goes

The robot drives around a room it has never seen and the 3D scene appears by
itself:

```
Phase A   LiDAR SLAM        ->  2D occupancy grid, walls and free space
Phase B   RGB-D camera      ->  3D point cloud of the room
Phase C   VLM labelling     ->  "that cluster is a desk, that one is a chair"
Phase D   Scene generation  ->  USD prims written into Omniverse automatically
```

Phase D replaces the hand written `_create_room()` with a function that consumes
the labelled reconstruction. `create_scene.py` stops being content and becomes a
renderer.

**The research question worth stating plainly:** how accurate is an
automatically generated Digital Twin compared with a hand authored one, and does
the difference matter for the twin's predictions?

That is a measurable question. Build the room by hand, build it automatically,
run the same missions in both, compare. Nobody can accuse that of being vague.

## Techniques, roughly in order of difficulty

| Approach | Output | Difficulty |
|---|---|---|
| 2D occupancy grid from LiDAR | floor plan | already in your plan |
| RTAB-Map with an RGB-D camera | dense 3D mesh | moderate, well documented |
| 3D Gaussian Splatting | photorealistic 3D | harder, needs a GPU, current research |
| Open vocabulary scene graph | labelled objects | hardest, active research |

Start at the top. A floor plan generated from real LiDAR data, replacing the
typed array, is already a complete result and it is achievable.

---

# Part 5. Solving the real pain

"Solve the current pain of the robot" is the right instinct, but it needs to be
specific or it becomes a wish list. Here are the actual pains, each tied to a
line of your code, and what fixes each.

| Pain | Where it lives now | Fix |
|---|---|---|
| The map is typed by hand | `grid_map.py:13` | SLAM occupancy grid |
| Dirt is a random number | `grid_map.py:44` | **Camera plus VLM** |
| Thresholds are hardcoded | `rules.py:101` | Learn per robot baselines |
| One robot only | `state-engine/main.py:44` | Key state by `robot_id` |
| The path never adapts | `grid_map.py:52` | Plan from the semantic map |
| The 3D view polls | `live_update.py:64` | Subscribe to MQTT |
| The scene is hand authored | `create_scene.py` | Generate from reconstruction |

Notice that **four of these seven are limitations you already identified and told
Dr about**. That is why volunteering them was worth doing. They are now a
roadmap rather than a list of things you missed.

## The one that changes behaviour most

Right now the robot follows a fixed lawnmower path regardless of what it finds.
With a semantic map it can decide:

- Skip the area under the desk, there are cables
- This section is carpet, slow down and turn the brush up
- This corner was dirty yesterday and is dirty again, visit it first
- A chair has moved since the last map, replan around it

That is the difference between a robot that executes a pattern and a robot that
makes decisions. It is also where the Digital Twin earns its place, because
those decisions are made against the twin's model of the room, not against raw
sensor readings.

---

# Part 6. Honest staging

The single biggest risk is trying all of this at once and finishing none of it.

| Year | Focus | Deliverable |
|---|---|---|
| **1** | Hardware and the bridge | Real robot appears in the existing dashboard. LiDAR SLAM replaces `grid_map.py`. |
| **2** | Vision and semantics | Camera plus VLM produces real `dirt_score`. Semantic labels on the map. Adaptive cleaning behaviour. |
| **3** | Self building twin, and VLA if it is ready | Omniverse scene generated from reconstruction. Sim to real gap measured. |

**Do not put VLA in year one.** It is the least mature piece and depends on
everything else working first. Naming it as a year three direction shows
awareness. Promising it in year one invites a reviewer to ask how, and there is
no good answer yet.

## Compute reality

| Where the VLM runs | Cost | Latency | Verdict |
|---|---|---|---|
| Workstation, robot streams frames | uses what you have | 1 to 3 s | **Start here** |
| Jetson Orin Nano 8 GB, onboard | ~RM 2,000 | 2 to 5 s, small models only | Later |
| Jetson AGX Orin, onboard | ~RM 8,000 | under 1 s | Only if untethered operation is a requirement |

Your MQTT architecture makes the first option nearly free to try, because the
robot only has to publish frames to a topic. Prove the idea that way before
spending anything on onboard compute.

---

# Part 7. What to say to Dr

> "The vision direction splits into three parts with very different maturity.
> VLMs for perception work today, and the first target is `dirt_score`, a field
> already in my schema that has no physical sensor. Semantic mapping on top of
> SLAM is achievable and is where the interesting behaviour comes from, because
> the robot can then plan against meaning rather than geometry. VLA for direct
> action is genuinely research grade and mostly targets manipulation rather than
> mobile robots, so I would position it as a later objective rather than promise
> it early.
>
> The architecture already supports all of it. Vision becomes a service that
> subscribes to a topic, exactly like the AI service does now, so adding it
> changes none of the six services that exist. And the VLM does not need to run
> on the robot, which keeps the hardware cost down while the idea is being
> proven."

That answer shows the idea is understood, staged, and costed, which is a
different impression from agreeing enthusiastically to everything.
