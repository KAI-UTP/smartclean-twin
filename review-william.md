1. Telemetry Message Trace
Hop 1 — Robot Simulator to MQTT Broker

The Robot Simulator Service creates a telemetry message representing the current condition of robot SCR01. The payload is formatted as JSON and contains information such as the robot ID, timestamp, position, heading, obstacle distance, battery condition, motor condition, dirt score, and cleaning actuator status.

The simulator publishes this JSON payload to the MQTT topic smartclean/SCR01/telemetry/raw. The message is transmitted to the Eclipse Mosquitto broker using MQTT over TCP through port 1883, allowing the simulator to publish data without needing a direct connection to each downstream service.

Hop 2 — MQTT Broker to Telemetry Ingestion Service

The Telemetry Ingestion Service subscribes to smartclean/SCR01/telemetry/raw through the Mosquitto broker. When the message arrives, the service decodes the JSON payload and validates it against the telemetry schema, including required fields, expected data types, robot identity, timestamps, and acceptable sensor ranges.

If the message is valid, the ingestion service adds processing metadata such as a server-received timestamp and prepares the telemetry for storage and downstream processing. Invalid messages should be rejected and recorded as validation events rather than being passed to the State Engine or AI Service. The project architecture assigns this service responsibility for validating raw telemetry, writing it to InfluxDB, and forwarding valid information to the other Digital Twin services.

Hop 3 — Telemetry Ingestion Service to InfluxDB

The validated telemetry is written to InfluxDB under the measurement robot_telemetry. The write operation uses the InfluxDB API on port 8086; although the original application message is JSON, the InfluxDB client converts it into InfluxDB line-protocol data for storage.

The robot ID can be stored as a tag, while values such as position, battery percentage, obstacle distance, motor temperature, motor current, and dirt score are stored as fields. The original event timestamp is retained so that the system can reconstruct the robot’s historical behaviour and distinguish robot event time from server processing time. The project contract specifies /api/v2/write, HTTP, port 8086, and line protocol for database writes.

Hop 4 — InfluxDB to Grafana

Grafana is configured with InfluxDB as its data source and sends Flux queries to retrieve recent records from robot_telemetry. These queries can filter the records by robot_id, measurement, field, and selected dashboard time range before displaying values in time-series graphs, status panels, gauges, tables, and alerts.

The dashboard automatically refreshes every five seconds. This interval provides near-real-time monitoring while avoiding an unnecessary query for every simulator update; therefore, a new telemetry message should normally become visible within approximately zero to five seconds after it is stored. The same five-second refresh approach was justified in the project visualization work as a balance between responsiveness and database-query load.

2. Microservice Design Assessment

The service separation is generally appropriate because each custom service has one main responsibility:

| Component           | Main responsibility                                                                       | Assessment                         |
| ------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------- |
| Robot Simulator     | Simulate movement, sensors, actuators, faults, and command responses                      | Clearly single-purpose             |
| Telemetry Ingestion | Subscribe, decode, validate, timestamp, and store incoming telemetry                      | Clearly single-purpose             |
| State Engine        | Convert valid telemetry into robot, safety, battery, cleaning, mission, and health states | Clearly single-purpose             |
| AI Service          | Produce classifications or predictions from telemetry                                     | Clearly single-purpose             |
| Command API         | Accept REST commands and publish them to MQTT                                             | Clearly single-purpose             |
| Mosquitto           | Route MQTT messages between publishers and subscribers                                    | Appropriate infrastructure service |
| InfluxDB            | Persist timestamped telemetry, states, predictions, and events                            | Appropriate infrastructure service |
| Grafana             | Query and visualize live and historical Digital Twin data                                 | Appropriate infrastructure service |


The separation between Telemetry Ingestion and the State Engine is useful. Telemetry validation is an interface concern, whereas state calculation is Digital Twin business logic; keeping them separate prevents an invalid message from entering the state model and allows either service to be tested or scaled independently.

For a very small classroom prototype, Telemetry Ingestion and the State Engine could have been combined to reduce the number of containers and internal connections. However, I would retain the current split because it provides clearer module boundaries, supports independent testing, and better satisfies the project requirement for well-defined microservices and interface contracts. The assignment also expects complete service partitioning, containerization, integration testing, persistence, and full Digital Twin flow, so the modular design is more suitable for the assessed system.

I would not split the State Engine further at the current scale. Creating separate services for safety, battery state, cleaning coverage, and mission progress would increase deployment and communication complexity without providing a clear benefit for a single simulated robot. Such separation would become more reasonable only if these functions required independent scaling or were reused across a larger robot fleet.

The architecture is also replaceable at the system boundary: the Robot Simulator can later be replaced by a physical robot gateway while the broker, ingestion, state processing, storage, visualization, and command services remain unchanged. This is one of the main strengths of the design.

3. Contract Verification

The three topic names are consistent with the MQTT topic list documented for SmartClean Twin.

Topic in docs/api-contract.md	Matches code?
| Topic in `docs/api-contract.md`   | Matches code? |
| --------------------------------- | ------------- |
| `smartclean/SCR01/telemetry/raw`  | **Yes**       |
| `smartclean/SCR01/state`          | **Yes**       |
| `smartclean/SCR01/command/motion` | **Yes**       |


The comparison should be based on exact string matching because MQTT topic names are case-sensitive. A difference in capitalization, spelling, separators, or robot ID would cause publishers and subscribers to use different communication channels even though the names appear visually similar.

Using shared constants in shared/smartclean_common/topics.py is a good design choice because it reduces duplicated topic strings across services. It also lowers the risk that the simulator, ingestion service, State Engine, and Command API will use inconsistent topic names.

4. Improvement Suggestions

1. Secure the MQTT communication

The prototype uses the standard MQTT port 1883, and there is no evidence in the provided contract that authentication or encryption is enabled. This means that another client with network access could potentially subscribe to telemetry, publish false robot data, or send unauthorized movement commands.

A production version should enable Mosquitto username/password authentication, topic-level access-control lists, and TLS encryption on port 8883. For example, the simulator should be allowed to publish telemetry and acknowledgements but should not be allowed to publish operator commands.

2. Improve multi-robot support

The current topic structure contains the fixed robot identifier SCR01. This is suitable for the initial demonstration but would require duplicated configuration when additional robots are introduced.

The topic structure should be generated from a robot identifier, such as:

smartclean/{robot_id}/telemetry/raw
smartclean/{robot_id}/state
smartclean/{robot_id}/command/motion

Services could then subscribe using patterns such as smartclean/+/telemetry/raw. InfluxDB should also store robot_id as a tag so Grafana can filter or compare multiple robots. The proposal already identifies multi-robot operation and coordination as possible future extensions.

3. Add stronger delivery and duplicate protection

Important state and command messages should use an appropriate MQTT Quality of Service level, particularly QoS 1 for commands and acknowledgements. Each message should include a unique message_id or command_id, sequence number, and timestamp so that receiving services can detect duplicates and out-of-order messages.

The robot should also use an MQTT Last Will and Testament message to indicate an unexpected disconnection. A retained connection-state message would allow a newly started dashboard or State Engine instance to immediately determine whether the robot is online.

4. Add schema versioning and invalid-message handling

Each telemetry payload should contain a field such as "schema_version": "1.0". This would allow the services to identify message-format changes when new sensors or actuators are introduced.

Messages that fail validation should be sent to a dedicated topic such as smartclean/SCR01/telemetry/invalid or stored in an ingestion-error measurement. This would preserve evidence for debugging without allowing corrupted data to affect the robot state, AI predictions, or dashboard.

5. Define retention and aggregation policies

Raw telemetry may grow quickly if the simulator publishes continuously. InfluxDB should therefore have a retention policy for high-resolution raw data and scheduled aggregation for long-term records.

For example, full-resolution data could be retained for 30 days, while one-minute averages, minimums, maximums, mission summaries, and alarm records could be retained for a longer period. This would control storage growth while preserving useful historical information.

5. Overall Assessment

In my opinion, SmartClean Twin has a strong and logical architecture because telemetry generation, validation, state calculation, AI processing, storage, visualization, and command handling are separated into understandable components. MQTT supports loosely coupled and bidirectional communication, while InfluxDB and Grafana provide suitable persistent storage and near-real-time visualization. The main weaknesses are the fixed single-robot topic structure, the apparent lack of MQTT authentication and encryption, and the need for clearer reliability mechanisms such as QoS selection, duplicate detection, retained states, and offline handling. Overall, the architecture is appropriate for a software-emulated prototype and provides a good foundation for future physical-robot and multi-robot integration.
