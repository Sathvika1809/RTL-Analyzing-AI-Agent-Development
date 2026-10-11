# Plan
intro, title selection, understanding the problem & key words - 1 week 
approach/design- 2 / 3 weeks (Design with architectural block diagrams and a clear explanation of logic)
RTL development - 6 / 7 weeks
--------------------------------------------------------------------------
# Assignment
Task 1 - Hardware Im2Col Implementation -- LEON
Task 2 - Multi-Systolic Array Communication -- SAIKIRTHAN
Task 3 - Mixed-Precision Processing Element (PE) Design -- PRATHAM
Task 4 - Remote Memory Access (RMA) hardware block -- KRISHNA
Task 5 - RTL Analysing AI Agent Development -- SATHVIKA
--------------------------------------------------------------------------
#Task 1: Hardware Im2Col Implementation
In deep learning workloads, convolutions are typically transformed into General Matrix Multiplications (GEMM) via the im2col process. In software, this involves significant data reorganization and copying in memory, which is inefficient for high-performance hardware.

##Your Objective:
Design a hardware-level data orchestration unit that performs "Implicit Im2Col." You must create a mechanism that fetches feature map data from memory and streams it directly to the compute units in the required matrix format without performing explicit data copying or re-buffering in memory.

##Key Design Challenges:
Address Generation Strategy: Develop a robust addressing logic that can transform multidimensional spatial data access into a linear stream compatible with your compute array input.

Data Flow: Define how the hardware will handle strides, padding, and feature map dimensions dynamically.

Throughput: Ensure your design can feed the compute units at full utilization, minimizing stalls due to memory latency or data alignment issues.

--------------------------------------------------------------------------
#Task 2: Multi-Systolic Array Communication
As we scale our compute capacity, a single systolic array is no longer sufficient. We are moving toward a multi-tile architecture where multiple systolic arrays must operate in tandem to accelerate training.

##Your Objective:
Design the communication fabric (interconnect) that links multiple systolic array tiles. This system must handle data sharing, partial sum aggregation, and the synchronization required for large-scale training workloads.

##Key Design Challenges:
Network Topology: Propose a scalable interconnect architecture that allows efficient data exchange between multiple arrays. Evaluate your choice based on area, power, and latency.

Communication Protocol: Define the handshaking and flow control mechanisms required to ensure data integrity as it moves between tiles.
System Synchronization: Design a global control strategy that ensures all arrays remain in lockstep during execution. Your design must guarantee that compute tiles can coordinate their operations, share partial results, and maintain pipeline alignment throughout the training process.

Approach and Deliverables
To succeed in these tasks, do not start with code. Follow this engineering process:

Functional Specification: Document the logic of your proposed design. Use diagrams to map out the data path, control signals, and state transitions.

Trade-off Analysis: You will face conflicting requirements (e.g., lower latency vs. lower gate count). Clearly document why you chose a specific architecture over alternatives.

Synthesizability: Keep in mind that your final design must be implemented in RTL. Ensure your architectural decisions are feasible for hardware synthesis and timing closure.

--------------------------------------------------------------------------
# Task 3: Mixed-Precision Processing Element (PE) Design

## Problem Statement
Modern AI training workloads require hardware that balances high throughput with extreme power and area efficiency. While specialized, separate execution units for different data types offer high performance, they introduce unacceptable area and power overheads in a systolic array.

The challenge lies in designing a unified, high-utilization Processing Element (PE) that handles both low-precision integer (**INT4**) and floating-point (**FP8**) matrix multiplications without duplicating hardware. The design must operate within strict physical constraints: a fixed **32-bit datapath** and a compute engine built entirely around base **8-bit multipliers** integrated into a **Fused Multiply-Accumulate (FMAC)** pipeline.


## Objective
Architect the microarchitecture for a unified, mixed-precision PE for an output-stationary systolic array. The execution unit must maximize hardware reuse by natively supporting both INT4 and FP8 operations within a shared FMAC pipeline.

The system must achieve:
* **Two independent INT4 multiplications per cycle** by fracturing a single $8 \times 8$-bit multiplier.
* **Exactly one FP8 MAC operation per cycle** with zero intermediate rounding.
* **Seamless data unpacking** of a 32-bit input payload into the appropriate precision streams without stalling the systolic pipeline.

## Challenges
A. Fracturing the 8-Bit Multiplier within an FMAC
To maintain strict area and power budgets, separate FP8 and INT4 MAC units cannot be instantiated. Hardware must be shared at the gate level:

* **The FP8 Challenge:** The FP8 pipeline must sustain a throughput of exactly 1 MAC/cycle. Because it is a Fused MAC, there can be no intermediate rounding between the multiplier and the adder. Exponent extraction, mantissa multiplication, alignment shifting, and 32-bit accumulation must operate continuously without pipeline stalls.
* **The INT4 Challenge:** To maximize compute density, a single $8 \times 8$ multiplier must be strategically utilized to perform two independent $4 \times 4$ multiplications simultaneously. The design must handle input packing and partial product isolation to prevent data collision between the two distinct low-precision products.

B. Managing the 32-Bit Datapath
The network feeding the systolic array and the internal routing paths are fixed at 32 bits wide, introducing bandwidth and alignment constraints:

* **Payload Constraints:** A 32-bit bus carries either four discrete FP8 values or eight discrete INT4 values per cycle.
* **Routing & Unpacking:** The PE edge logic must slice, register, and route this 32-bit payload to the computing structures over the correct clock cycles.
* **Mode Switching:** The control logic must seamlessly switch unpacking modes based on the active precision configuration without introducing pipeline bubbles.

## Approach and Deliverables
A. Datapath Microarchitecture
Provide a detailed structural breakdown and block diagram of the internal PE architecture. The specification must explicitly detail the core structural components:
* **Input Slicing & Registration** * 
 **Multiplier Fracturing Strategy**


B. Format Handling & Throughput
* **FP8 Formats:** Detail support for standard Open Compute Project (OCP) formats, explicitly mapping both **E4M3** (for weights/activations) and **E5M2** (for gradients) into the shared hardware logic.
* **Execution Profiling:** Step through the operation sequence to demonstrate stable execution boundaries for both data types.

--------------------------------------------------------------------------
# Task 4: Remote Memory Access (RMA) hardware block
1. Problem Statement
Distributed AI workloads require rapid tensor exchanges between adjacent accelerators. Remote Memory Access (RMA) bypasses the host CPU, OS kernel, and system RAM entirely, allowing accelerators to stream data directly into each other’s local SRAM/HBM over a high-speed fabric. However, in multi-tenant clusters, orchestrating these asynchronous transfers securely and without deadlocks presents a major hardware routing and synchronization bottleneck.

2. Objective
Design and implement a secure, high-throughput Peer-to-Peer (P2P) DMA and Fabric Subsystem (dma_p2p_engine.sv, sar_tx.sv, sar_rx.sv) that orchestrates direct SRAM-to-SRAM tensor data movement between local and remote accelerators sharing the same active Context ID (ctx_id). The system must securely translate context-relative virtual descriptors, ordering fence constraints, and 1D context-indexed synchronization with zero host CPU intervention.

Key Challenges

Line-Rate Packet Segmentation & Reassembly (SAR): Large tensor transfers (up to 16 KB) cannot monopolize the fabric without causing network deadlocks and blocking compute cycles. The sar_tx.sv and sar_rx.sv blocks must transparently slice descriptors into 256-Byte chunks with a 19-bit routing fabric header, while tracking sequence integrity and handling packet-level ACKs/NACKs in-flight.

Multi-Tenant 1D Scoreboard Synchronization: Accelerators must resolve data dependencies entirely in hardware without CPU coordination. The scoreboard_1d.sv must be designed to track a single aggregated inflight transaction counter for each of the 64 distinct contexts ($64 \times 1$ tracking array), ensuring asynchronous RMA operations safely trigger and release local execution boundaries per tenant.

Fence Enforcement & Deadlock Prevention: Asynchronous RMA writes can arrive out-of-order or trigger network backpressure, causing cluster-wide deadlocks if a context-scoped Fence instruction stalls the queue indefinitely. The fence logic must couple with the scoreboard_1d.sv and mac_arbiter.sv to automatically escalate the priority of incoming packets associated with the blocked ctx_id until its outstanding transaction count drops to zero.

##Approach:
Design a context-aware P2P DMA engine that validates every transfer using hardware-enforced base-and-bounds checks to ensure secure multi-tenant isolation across 64 contexts.
Implement SAR TX/RX modules to segment large tensor transfers into 256-byte packets, attach routing/sequence metadata, and support ACK/NACK-based reliable delivery.
Integrate a deadlock-aware MAC arbiter that dynamically boosts packet priority for fence-blocked contexts to drain pending transactions and prevent starvation.
Pipeline validation, segmentation, routing, reassembly, and synchronization stages to achieve high-throughput SRAM-to-SRAM tensor movement with zero host CPU intervention.

Deliverables:
Complete RTL design and testbench for verifying various test cases
--------------------------------------------------------------------------
# Task 5:  RTL Analysis AI Agent Development

##Problem Statement:
Modern RTL/SystemVerilog design and verification cycles involve large codebases with increasing architectural complexity, deep pipelining, multiple clock/reset domains, parameterized modules, and aggressive PPA (Power, Performance, Area) targets. Traditional linting and simulation tools are effective at detecting syntactic and structural issues but often lack contextual reasoning for:
Architectural inefficiencies, Pipeline hazards, Weak coding practices, Missing assertions and verification intent, Potential synthesis/timing bottlenecks, Readability and maintainability concerns

Engineers spend significant manual effort reviewing RTL for Bug identification, Design consistency checks, Verification planning etc. There is a need for an intelligent agent-based RTL analysis framework capable of:
Understanding RTL intent
Performing contextual code analysis
Suggesting fixes and optimizations
Generating assertions and verification guidance
Scaling across multiple files/modules automatically

using locally deployable LLM-based agents integrated into the RTL development workflow.

## Objective
The objective of this work is to develop an AI-agent-based RTL assistant capable of automated SystemVerilog code analysis and enhancement using local LLM inference frameworks such as Ollama.
The proposed framework aims to Analyze RTL/SystemVerilog files automatically and Identify Coding bugs, Latch inference risks. Timing and pipeline concerns, Assertion suggestions (SVA) etc. 


## Challenges
Large Language Models are probabilistic in nature and may Produce inconsistent outputs or Generate incomplete or hallucinated RTL/SVA. 
Ensuring deterministic and synthesizable output remains a key challenge.

## Approach and Deliverables

The work will follow a staged agent-based development methodology.

Phase 1 — Environment Setup and Baseline Evaluation
Install and configure frameworks like Ollama & backend LLMs to Evaluate model behavior on RTL tasks like Code analysis, Bug identification, Assertion generation etc.

Phase 2 — RTL Analysis Agent Development
Develop Python-based automation framework to Parse multiple RTL files, Perform file-level analysis and Generate Analysis reports, Suggested RTL improvements, Structured output extraction utilities

Phase 3 — Agent Specialization
Introduce specialized agents for Bug analysis, Timing/pipeline review, Assertion generation, Code optimization


At the end of the effort, the project is expected to deliver A prototype AI-agent RTL assistant, Automated RTL review capability, SVA generation support, Multi-file analysis flow, Extensible architecture for future EDA integration

along with documented observations on the practicality and limitations of local LLM-based RTL engineering assistants.