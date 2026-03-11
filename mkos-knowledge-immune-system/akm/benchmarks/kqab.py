"""KQAB: Knowledge Quality Assurance Benchmark.

A benchmark for evaluating knowledge base quality assurance systems.
Four tasks covering the full spectrum of KB quality problems:

  T1: Threat Detection     - Classify chunks as healthy/hallucination/staleness/bias/contradiction
  T2: Contradiction Discovery - Given a chunk pair, classify as contradicts/consistent/unrelated
  T3: Temporal Decay       - Given a chunk, classify as current/outdated/deprecated
  T4: Evidence Grounding   - Given a claim + KB context, classify as supported/unsupported/partial

Each task includes datasets for two domains:
  - Software Engineering (internal KB simulation)
  - General Knowledge (Wikipedia-based)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from akm.benchmarks.datasets import BenchmarkItem
from akm.benchmarks.metrics import ClassificationMetrics


# ── Task Definitions ──────────────────────────────────────────────────────


@dataclass
class KQABTask:
    """A single KQAB benchmark task."""
    task_id: str       # T1, T2, T3, T4
    name: str
    description: str
    labels: list[str]
    items: list[BenchmarkItem] = field(default_factory=list)
    domain: str = "software_engineering"  # or "general_knowledge"

    @property
    def size(self) -> int:
        return len(self.items)


@dataclass
class KQABResult:
    """Result of running a system on one KQAB task."""
    task_id: str
    system_name: str
    predictions: list[str]
    ground_truth: list[str]
    duration_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def per_class_metrics(self) -> dict[str, dict]:
        classes = sorted(set(self.ground_truth) | set(self.predictions))
        result = {}
        for cls in classes:
            m = ClassificationMetrics()
            for pred, truth in zip(self.predictions, self.ground_truth):
                if pred == cls and truth == cls:
                    m.true_positives += 1
                elif pred == cls and truth != cls:
                    m.false_positives += 1
                elif pred != cls and truth == cls:
                    m.false_negatives += 1
                else:
                    m.true_negatives += 1
            result[cls] = m.to_dict()
        return result

    @property
    def macro_f1(self) -> float:
        per_class = self.per_class_metrics
        f1s = [v["f1"] for v in per_class.values()]
        return sum(f1s) / len(f1s) if f1s else 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "system": self.system_name,
            "n_items": len(self.predictions),
            "macro_f1": round(self.macro_f1, 4),
            "per_class": self.per_class_metrics,
            "duration_seconds": round(self.duration_seconds, 2),
            "metadata": self.metadata,
        }


# ── T2: Contradiction Discovery ──────────────────────────────────────────


@dataclass
class ChunkPair:
    """A pair of chunks for contradiction discovery."""
    chunk_a: str
    chunk_b: str
    label: str  # contradicts, consistent, unrelated
    metadata: dict = field(default_factory=dict)


def t2_contradiction_dataset() -> list[ChunkPair]:
    """Generate contradiction discovery pairs for T2.

    Returns pairs labeled as contradicts/consistent/unrelated.
    Mix of SE-domain and general knowledge.
    """
    pairs = []

    # --- Contradicting pairs ---
    # Mix of obvious (O) and subtle (S) contradictions.
    # Subtle ones are designed to be harder: both chunks sound plausible,
    # but they make incompatible factual claims.
    contradictions = [
        # S: Both sound like valid design advice, but conflict on error handling approach
        ("In REST API design, the server should use HTTP status codes semantically: 200 for success, 404 for missing resources, 422 for validation errors. This follows RFC 7231 and makes APIs predictable for clients.",
         "A well-designed REST API should return 200 OK for all successful operations and include a status field in the JSON body. Using HTTP status codes for application-level errors conflates transport and application concerns.",
         {"domain": "se", "topic": "rest_design", "difficulty": "subtle"}),

        # S: Subtle disagreement on Python's GIL impact
        ("Python's GIL (Global Interpreter Lock) prevents true parallelism for CPU-bound tasks, but I/O-bound tasks can still benefit from threading because the GIL is released during I/O operations.",
         "Python's GIL prevents any performance benefit from threading, even for I/O-bound workloads. The overhead of thread management always outweighs any concurrency gains, which is why asyncio was created as a replacement.",
         {"domain": "se", "topic": "python_gil", "difficulty": "subtle"}),

        # S: Subtle disagreement on when to use microservices
        ("Microservices are most beneficial for large teams (50+ engineers) where organizational boundaries align with service boundaries. For small teams, the operational overhead usually outweighs the benefits.",
         "Microservices should be adopted from the start of any new project, regardless of team size. Refactoring a monolith later is always more expensive than designing with services from day one.",
         {"domain": "se", "topic": "microservices_adoption", "difficulty": "subtle"}),

        # S: Disagreement on NoSQL vs SQL for consistency
        ("MongoDB provides strong consistency by default within a single document. For multi-document operations, it offers ACID transactions since version 4.0, making it suitable for financial applications.",
         "MongoDB only provides eventual consistency and cannot guarantee ACID properties. Any application requiring transactional consistency must use a relational database like PostgreSQL.",
         {"domain": "se", "topic": "mongodb_consistency", "difficulty": "subtle"}),

        # S: Subtle disagreement on container security
        ("Docker containers provide process isolation through Linux namespaces and cgroups, but they share the host kernel. A kernel vulnerability can potentially affect all containers, so defense-in-depth is essential.",
         "Docker containers provide complete security isolation equivalent to virtual machines. Each container runs in its own sandbox with no shared attack surface with the host or other containers.",
         {"domain": "se", "topic": "container_security", "difficulty": "subtle"}),

        # S: Subtle disagreement on GraphQL vs REST performance
        ("GraphQL can reduce the number of network requests by allowing clients to fetch all needed data in a single query. However, complex GraphQL queries can be more expensive on the server than equivalent REST endpoints due to the N+1 problem.",
         "GraphQL always outperforms REST in terms of both network efficiency and server-side performance. The query resolver pattern ensures optimal database access patterns automatically.",
         {"domain": "se", "topic": "graphql_performance", "difficulty": "subtle"}),

        # S: Subtle disagreement on testing strategies
        ("Unit tests should mock external dependencies to test business logic in isolation. Integration tests then verify that components work together correctly. This test pyramid approach minimizes maintenance costs.",
         "Mocking in unit tests creates a false sense of security because the mocks may not match real behavior. All tests should use real dependencies, and the testing pyramid is an outdated pattern.",
         {"domain": "se", "topic": "testing_strategy", "difficulty": "subtle"}),

        # O: Obvious contradiction on Git internals
        ("Git uses a directed acyclic graph (DAG) to store commit history, where each commit points to its parent(s).",
         "Git stores commits in a linear linked list structure, which is why rebasing is impossible without data loss.",
         {"domain": "se", "topic": "git_internals", "difficulty": "obvious"}),

        # O: Obvious contradiction on TCP
        ("TCP provides reliable, ordered delivery of data through sequence numbers and acknowledgments.",
         "TCP does not guarantee ordered delivery; packets may arrive in any order and the application must handle reordering.",
         {"domain": "se", "topic": "tcp", "difficulty": "obvious"}),

        # S: Subtle disagreement on Kubernetes overhead
        ("Kubernetes adds approximately 10-15% resource overhead for the control plane and sidecars. For clusters with fewer than 10 services, this overhead may exceed the benefits of orchestration.",
         "Kubernetes has negligible resource overhead. The control plane uses minimal resources, and the orchestration benefits apply even for single-service deployments.",
         {"domain": "se", "topic": "k8s_overhead", "difficulty": "subtle"}),

        # S: Subtle disagreement on type systems
        ("TypeScript's type system is structural, meaning types are compatible if their structures match, regardless of explicit declarations. This enables duck typing with static analysis benefits.",
         "TypeScript uses a nominal type system where types are only compatible if they are explicitly declared to be. Two interfaces with identical fields are incompatible unless one extends the other.",
         {"domain": "se", "topic": "typescript_types", "difficulty": "subtle"}),

        # S: General knowledge - subtle disagreement on sleep science
        ("Adults need 7-9 hours of sleep per night for optimal cognitive function. Sleep deprivation accumulates as 'sleep debt' that can only be repaid by extra sleep.",
         "Individual sleep needs vary widely from 4-10 hours. Short sleepers who naturally need only 4-5 hours show no cognitive impairment, and the concept of sleep debt has been debunked by recent studies.",
         {"domain": "general", "topic": "sleep_science", "difficulty": "subtle"}),

        # S: Subtle disagreement on climate science mechanism
        ("CO2 absorbs infrared radiation at specific wavelengths, creating a greenhouse effect that warms the atmosphere. The relationship between CO2 concentration and temperature is logarithmic, meaning each doubling produces roughly the same warming increment.",
         "The relationship between CO2 and temperature is linear: each additional unit of CO2 produces the same amount of warming regardless of the current concentration. There is no saturation effect.",
         {"domain": "general", "topic": "climate_physics", "difficulty": "subtle"}),

        # O: Obvious contradiction on Rust
        ("Rust's ownership system prevents data races at compile time without needing a garbage collector.",
         "Rust uses a traditional garbage collector that runs periodically, similar to Java's approach to memory management.",
         {"domain": "se", "topic": "rust_ownership", "difficulty": "obvious"}),

        # S: Subtle disagreement on database indexing
        ("Adding indexes to database columns speeds up read queries but slows down write operations because each insert/update must also update the index. Over-indexing is a common performance anti-pattern.",
         "Modern database engines optimize index maintenance so effectively that the write overhead of additional indexes is negligible. Databases should index every column that appears in a WHERE clause.",
         {"domain": "se", "topic": "db_indexing", "difficulty": "subtle"}),
    ]

    for a, b, meta in contradictions:
        pairs.append(ChunkPair(chunk_a=a, chunk_b=b, label="contradicts", metadata=meta))

    # --- Consistent pairs ---
    consistent = [
        ("Python lists are implemented as dynamic arrays that automatically resize when needed.",
         "When a Python list exceeds its allocated capacity, it allocates a new, larger array and copies elements over.",
         {"domain": "se", "topic": "python_lists"}),

        ("Kubernetes orchestrates container deployments across a cluster of machines.",
         "K8s manages the lifecycle of containers, handling scaling, networking, and health checks automatically.",
         {"domain": "se", "topic": "kubernetes"}),

        ("React uses a virtual DOM to minimize expensive real DOM operations.",
         "React's reconciliation algorithm compares the virtual DOM with the previous version and applies only the necessary changes to the real DOM.",
         {"domain": "se", "topic": "react_vdom"}),

        ("Hash tables provide O(1) average-case lookup by mapping keys through a hash function.",
         "A hash map stores key-value pairs using a hash function to compute the storage index, achieving constant-time average access.",
         {"domain": "se", "topic": "hashtable"}),

        ("PostgreSQL supports ACID transactions ensuring data integrity across concurrent operations.",
         "Postgres uses MVCC (Multi-Version Concurrency Control) to provide transaction isolation without blocking readers.",
         {"domain": "se", "topic": "postgres"}),

        ("The human genome contains approximately 3 billion base pairs of DNA.",
         "Human DNA consists of about 3 billion nucleotide pairs organized into 23 pairs of chromosomes.",
         {"domain": "general", "topic": "genetics"}),

        ("Water boils at 100 degrees Celsius at standard atmospheric pressure.",
         "At sea level (1 atm), the boiling point of water is 100C or 212F.",
         {"domain": "general", "topic": "physics_water"}),

        ("Neural networks learn by adjusting weights through backpropagation of gradients.",
         "During training, neural networks compute error gradients and propagate them backwards to update connection weights.",
         {"domain": "general", "topic": "neural_nets"}),

        ("GraphQL allows clients to request exactly the data they need in a single query.",
         "With GraphQL, the client specifies the shape of the response, avoiding over-fetching and under-fetching common in REST.",
         {"domain": "se", "topic": "graphql"}),

        ("WebAssembly enables near-native performance for code running in web browsers.",
         "WASM is a binary instruction format that allows languages like C++ and Rust to run in the browser at close to native speed.",
         {"domain": "se", "topic": "wasm"}),
    ]

    for a, b, meta in consistent:
        pairs.append(ChunkPair(chunk_a=a, chunk_b=b, label="consistent", metadata=meta))

    # --- Unrelated pairs ---
    unrelated = [
        ("Python's asyncio module provides infrastructure for writing single-threaded concurrent code using coroutines.",
         "The Eiffel Tower was completed in 1889 and stands 330 meters tall in Paris, France.",
         {"domain": "mixed", "topic": "unrelated_1"}),

        ("Redis is an in-memory data structure store used as a database, cache, and message broker.",
         "Photosynthesis converts carbon dioxide and water into glucose and oxygen using light energy.",
         {"domain": "mixed", "topic": "unrelated_2"}),

        ("CSS Grid provides a two-dimensional layout system for web content.",
         "The mitochondria is often called the powerhouse of the cell because it generates most of the cell's ATP.",
         {"domain": "mixed", "topic": "unrelated_3"}),

        ("TypeScript adds static type checking to JavaScript at compile time.",
         "Mozart composed over 600 works during his 35-year lifetime.",
         {"domain": "mixed", "topic": "unrelated_4"}),

        ("Terraform uses declarative configuration files to manage infrastructure as code.",
         "The Amazon River is the largest river by discharge volume of water in the world.",
         {"domain": "mixed", "topic": "unrelated_5"}),

        ("CI/CD pipelines automate the build, test, and deployment process for software.",
         "The periodic table organizes chemical elements by atomic number and electron configuration.",
         {"domain": "mixed", "topic": "unrelated_6"}),

        ("MapReduce processes large datasets in parallel across a distributed cluster.",
         "The Great Wall of China spans approximately 21,196 kilometers across northern China.",
         {"domain": "mixed", "topic": "unrelated_7"}),

        ("Bloom filters are space-efficient probabilistic data structures that test set membership.",
         "Beethoven composed his Ninth Symphony while almost completely deaf.",
         {"domain": "mixed", "topic": "unrelated_8"}),

        ("JWT tokens encode claims as JSON and are commonly used for API authentication.",
         "The Mariana Trench is the deepest known point in Earth's oceans at about 11,034 meters.",
         {"domain": "mixed", "topic": "unrelated_9"}),

        ("gRPC uses Protocol Buffers for serialization and HTTP/2 for transport.",
         "The human body contains approximately 206 bones in adulthood.",
         {"domain": "mixed", "topic": "unrelated_10"}),
    ]

    for a, b, meta in unrelated:
        pairs.append(ChunkPair(chunk_a=a, chunk_b=b, label="unrelated", metadata=meta))

    return pairs


# ── T3: Temporal Decay ────────────────────────────────────────────────────


def t3_temporal_decay_dataset() -> list[BenchmarkItem]:
    """Generate temporal decay dataset for T3.

    Labels: current, outdated, deprecated.
    """
    items = []

    # --- Current items (80) ---
    current_se = [
        ("Python 3.12 introduces type parameter syntax using PEP 695.", "Python 3.12 Types"),
        ("React 18 adds concurrent rendering and automatic batching of state updates.", "React 18"),
        ("TypeScript 5.x supports decorators natively following the TC39 proposal.", "TypeScript 5 Decorators"),
        ("HTTP/3 uses QUIC protocol for faster, more reliable connections than TCP.", "HTTP/3 QUIC"),
        ("Rust 2024 edition introduces async trait methods.", "Rust 2024"),
        ("Docker Desktop supports running containers natively on Apple Silicon M-series chips.", "Docker M-series"),
        ("Node.js 20 LTS includes a built-in test runner and stable fetch API.", "Node.js 20"),
        ("PostgreSQL 16 adds logical replication from standby servers.", "PostgreSQL 16"),
        ("Kubernetes 1.29 introduces sidecar containers as a first-class concept.", "K8s 1.29"),
        ("CSS has native nesting support in all modern browsers since 2023.", "CSS Nesting"),
        ("Git 2.43 adds support for reftable backend for improved reference storage.", "Git 2.43"),
        ("SQLite 3.45 introduces jsonb storage format for faster JSON operations.", "SQLite 3.45"),
        ("Go 1.22 adds range-over-function iterators.", "Go 1.22"),
        ("Vue 3 Composition API is the recommended approach for new projects.", "Vue 3 Composition"),
        ("Deno 2.0 adds npm compatibility and removes permission prompts.", "Deno 2.0"),
        ("Bun 1.0 is a fast JavaScript runtime that includes a bundler, transpiler, and package manager.", "Bun 1.0"),
        ("Astro 4.0 supports server islands for mixing static and dynamic content.", "Astro 4.0"),
        ("Next.js 14 uses the App Router with React Server Components by default.", "Next.js 14"),
        ("Tailwind CSS 4.0 introduces a new engine built on Lightning CSS.", "Tailwind 4.0"),
        ("Vite 5 is the standard build tool for modern frontend frameworks.", "Vite 5"),
        ("pnpm is increasingly adopted as a faster, disk-efficient alternative to npm.", "pnpm"),
        ("Playwright has become the standard for cross-browser end-to-end testing.", "Playwright"),
        ("OpenTelemetry is the standard for distributed tracing and observability.", "OpenTelemetry"),
        ("SQLite is used as an application database in production by companies like Turso and Fly.io.", "SQLite Production"),
        ("Podman provides a daemonless container engine compatible with Docker CLI.", "Podman"),
        ("GitHub Copilot uses LLMs to provide AI-assisted code completion in IDEs.", "GitHub Copilot"),
        ("Zig is gaining adoption as a systems language with no hidden control flow.", "Zig"),
        ("HTMX enables dynamic HTML without writing JavaScript by using HTML attributes.", "HTMX"),
        ("Biome is a fast Rust-based linter and formatter replacing ESLint + Prettier.", "Biome"),
        ("WebGPU provides modern GPU access in browsers, replacing WebGL for new projects.", "WebGPU"),
        ("Terraform CDK allows defining infrastructure using TypeScript, Python, or Go.", "Terraform CDK"),
        ("Grafana Loki provides log aggregation designed to work with Prometheus.", "Grafana Loki"),
        ("Cilium uses eBPF for high-performance Kubernetes networking and security.", "Cilium eBPF"),
        ("Nix and NixOS provide reproducible builds and system configurations.", "Nix"),
        ("DuckDB is an embeddable OLAP database optimized for analytical queries.", "DuckDB"),
        ("Ollama enables running LLMs locally on consumer hardware.", "Ollama"),
        ("UV is a fast Python package installer and resolver written in Rust.", "UV Python"),
        ("Ruff is an extremely fast Python linter written in Rust.", "Ruff"),
        ("EdgeDB provides a graph-relational database with a built-in query language.", "EdgeDB"),
        ("Temporal.io provides durable execution for distributed systems workflows.", "Temporal"),
        ("Zod is the standard schema validation library for TypeScript applications.", "Zod"),
        ("tRPC enables end-to-end typesafe APIs between TypeScript frontend and backend.", "tRPC"),
        ("SvelteKit 2.0 provides a full-stack framework with server-side rendering.", "SvelteKit 2"),
        ("Turbopack is the Rust-based successor to Webpack, integrated with Next.js.", "Turbopack"),
        ("Effect-TS brings functional effect system patterns to TypeScript.", "Effect-TS"),
    ]

    current_general = [
        ("The James Webb Space Telescope began full science operations in 2022.", "JWST"),
        ("mRNA vaccine technology enables rapid development of vaccines against new variants.", "mRNA Vaccines"),
        ("ChatGPT and similar LLMs use transformer architecture for text generation.", "LLMs"),
        ("CRISPR-Cas9 gene editing is now used in clinical trials for genetic diseases.", "CRISPR"),
        ("Electric vehicles account for over 18% of global new car sales in 2024.", "EV Market"),
        ("Artemis program aims to return humans to the Moon, with Artemis II crewed flight planned.", "Artemis"),
        ("AlphaFold has predicted structures for nearly all known proteins.", "AlphaFold"),
        ("Fusion energy research achieved net energy gain at NIF in December 2022.", "Fusion NIF"),
        ("Solid-state batteries are expected to significantly improve EV range and charging speed.", "Solid-State Batteries"),
        ("SpaceX Starship is the largest and most powerful rocket ever built.", "Starship"),
        ("The WHO declared the end of COVID-19 as a public health emergency in May 2023.", "COVID End"),
        ("Large language models can pass professional exams including the bar and medical licensing.", "LLM Exams"),
        ("Quantum computing reached error-corrected logical qubits in 2024.", "Quantum Error Correction"),
        ("Global average temperature in 2024 exceeded 1.5C above pre-industrial levels.", "Climate 1.5C"),
        ("Neuralink received FDA approval for human clinical trials of brain-computer interfaces.", "Neuralink FDA"),
        ("Weight-loss drugs like semaglutide (Ozempic/Wegovy) show broader health benefits.", "GLP-1 Drugs"),
        ("Generative AI can create photorealistic images, video, and music from text prompts.", "Generative AI"),
        ("Open-source LLMs like Llama 3 and Mistral compete with proprietary models.", "Open Source LLMs"),
        ("Carbon capture technology is being deployed at industrial scale.", "Carbon Capture"),
        ("Gene therapy has received regulatory approval for sickle cell disease treatment.", "Gene Therapy SCD"),
        ("Autonomous drone delivery services are operational in multiple countries.", "Drone Delivery"),
        ("Perovskite solar cells are approaching commercial viability with 33%+ efficiency.", "Perovskite Solar"),
        ("The global semiconductor shortage has largely resolved by 2024.", "Chip Shortage End"),
        ("Digital twins are used in manufacturing, healthcare, and urban planning.", "Digital Twins"),
        ("Lab-grown meat received regulatory approval in the US and Singapore.", "Lab Grown Meat"),
        ("Room-temperature superconductors remain unconfirmed despite multiple claims.", "Superconductors"),
        ("Humanoid robots from Tesla, Figure, and others are in development and early deployment.", "Humanoid Robots"),
        ("Satellite internet constellations (Starlink, OneWeb) provide global broadband coverage.", "Satellite Internet"),
        ("Biodegradable plastics made from plant-based materials are commercially available.", "Bioplastics"),
        ("Vertical farming is scaling up to provide fresh produce in urban environments.", "Vertical Farming"),
        ("AI-powered drug discovery has accelerated clinical trials for new therapeutics.", "AI Drug Discovery"),
        ("Hydrogen fuel cells are being deployed for heavy transport and industrial use.", "Hydrogen Fuel Cells"),
        ("Brain organoids grown from stem cells are used to study neurological diseases.", "Brain Organoids"),
        ("Microplastics have been detected in human blood, lungs, and placental tissue.", "Microplastics"),
        ("6G research is underway with expected deployment around 2030.", "6G Research"),
    ]

    for content, title in current_se:
        items.append(BenchmarkItem(content=content, title=title, labels=["current"],
                                   metadata={"domain": "se"}))
    for content, title in current_general:
        items.append(BenchmarkItem(content=content, title=title, labels=["current"],
                                   metadata={"domain": "general"}))

    # --- Outdated items (80) ---
    outdated_se = [
        ("Python 3.6 is the latest stable release with f-string support.", "Python 3.6 Latest"),
        ("Angular 1.x (AngularJS) is the recommended framework for new web applications.", "AngularJS Recommended"),
        ("Java 8 is the current long-term support release with lambda expressions.", "Java 8 LTS"),
        ("Node.js 12 is in active LTS with improved ES module support.", "Node.js 12 LTS"),
        ("React class components are the standard way to build React applications.", "React Class Components"),
        ("Docker Swarm is the primary container orchestration tool for production workloads.", "Docker Swarm Primary"),
        ("MongoDB 3.6 introduces change streams for real-time data changes.", "MongoDB 3.6"),
        ("Vue 2 with the Options API is the current standard for Vue development.", "Vue 2 Options"),
        ("Ubuntu 18.04 LTS is the recommended server distribution.", "Ubuntu 18.04"),
        ("Webpack 4 is the standard build tool for modern JavaScript applications.", "Webpack 4"),
        ("TensorFlow 1.x with sessions is the standard API for deep learning.", "TensorFlow 1.x"),
        ("Swift 4 introduces Codable protocol for JSON serialization.", "Swift 4"),
        ("Redis 5.0 introduces Streams as a new data type.", "Redis 5.0"),
        ("Yarn 1.x is the preferred package manager for JavaScript projects.", "Yarn 1"),
        ("Create React App is the recommended way to start a new React project.", "CRA"),
        ("Enzyme is the standard testing library for React components.", "Enzyme"),
        ("Jest is the only JavaScript testing framework you need.", "Jest Only"),
        ("Moment.js is the standard library for date/time manipulation in JavaScript.", "Moment.js"),
        ("Lodash is essential for JavaScript development due to missing native methods.", "Lodash Essential"),
        ("Express.js 4 is the only production-ready Node.js web framework.", "Express Only"),
        ("Docker Compose v1 (docker-compose) is the standard for multi-container apps.", "Docker Compose v1"),
        ("Heroku is the leading platform for deploying web applications.", "Heroku Leading"),
        ("Travis CI is the most popular CI/CD service for open source projects.", "Travis CI"),
        ("Atom editor is a modern, hackable text editor for developers.", "Atom Editor"),
        ("Redux is required for state management in any React application.", "Redux Required"),
        ("Flow type checker is Facebook's recommended way to add types to JavaScript.", "Flow Types"),
        ("Lerna is the standard tool for managing JavaScript monorepos.", "Lerna"),
        ("TSLint is the standard linter for TypeScript projects.", "TSLint"),
        ("styled-components is the dominant CSS-in-JS solution for React.", "styled-components"),
        ("MySQL 5.7 is the current stable release with JSON support.", "MySQL 5.7"),
        ("PHP 7.0 introduces scalar type declarations and return types.", "PHP 7.0"),
        ("Kubernetes 1.18 introduces kubectl debug for troubleshooting.", "K8s 1.18"),
        ("Jenkins is the undisputed standard for CI/CD pipelines.", "Jenkins Standard"),
        ("Vagrant is the best tool for creating reproducible development environments.", "Vagrant"),
        ("Puppet and Chef are the leading configuration management tools.", "Puppet Chef"),
        ("OpenStack is the dominant private cloud platform.", "OpenStack"),
        ("Apache Kafka 2.0 introduces exactly-once semantics.", "Kafka 2.0"),
        ("Elasticsearch 6.x introduces sequence number-based optimistic concurrency.", "Elasticsearch 6"),
        ("React Native is the only viable cross-platform mobile framework.", "React Native Only"),
        ("Sass/SCSS preprocessing is essential for writing maintainable CSS.", "Sass Essential"),
    ]

    outdated_general = [
        ("The Higgs boson was recently discovered at CERN in 2012.", "Higgs Boson Recent"),
        ("Self-driving cars are expected to be widely available by 2020.", "Self-Driving 2020"),
        ("5G networks are in early testing and not yet commercially available.", "5G Early"),
        ("Pluto was reclassified as a dwarf planet in the recent IAU decision.", "Pluto Reclassified"),
        ("The International Space Station is scheduled for completion in 2011.", "ISS Completion"),
        ("CRISPR technology is purely theoretical and has not been tested in living organisms.", "CRISPR Theoretical"),
        ("Machine learning requires custom hardware; GPUs cannot be used for training.", "ML No GPU"),
        ("Tesla is a startup electric car company that has yet to achieve mass production.", "Tesla Startup"),
        ("Bitcoin is a niche digital currency used mainly by tech enthusiasts.", "Bitcoin Niche"),
        ("Cloud computing is an emerging trend that may replace traditional servers.", "Cloud Emerging"),
        ("Social media is primarily used by younger demographics and has limited business value.", "Social Media Limited"),
        ("Streaming services are a small niche market; most people prefer physical media.", "Streaming Niche"),
        ("3D printing is a novelty technology mainly used for prototyping.", "3D Printing Novelty"),
        ("Graphene will revolutionize electronics within the next 5 years.", "Graphene Soon"),
        ("Theranos is revolutionizing blood testing with its miniaturized technology.", "Theranos"),
        ("Google Glass will transform how we interact with information daily.", "Google Glass"),
        ("The ozone layer continues to deteriorate with no signs of recovery.", "Ozone Decline"),
        ("Smartphones are luxury devices that most people cannot afford.", "Smartphones Luxury"),
        ("Renewable energy is too expensive to compete with fossil fuels.", "Renewables Expensive"),
        ("AI winter continues and neural networks have proven to be a dead end.", "AI Winter"),
        ("The Mars Curiosity rover just landed and is beginning its mission.", "Curiosity Landing"),
        ("The COVID-19 pandemic is currently at its peak with no vaccines available.", "COVID Peak"),
        ("Quantum computers are at least 50 years away from practical applications.", "Quantum Far Away"),
        ("Electric cars have a maximum range of about 100 miles per charge.", "EV Range 100"),
        ("Virtual reality headsets are too expensive and bulky for consumer use.", "VR Expensive"),
        ("Gene therapy has never been successfully used to treat any human disease.", "Gene Therapy Untested"),
        ("Deep learning is a theoretical concept with no practical applications yet.", "DL Theoretical"),
        ("China is planning to build its first space station.", "China Space Station Planning"),
        ("GPT-2 is the most advanced language model available.", "GPT-2 Advanced"),
        ("Autonomous vehicles are illegal on public roads worldwide.", "AV Illegal"),
        ("Solid-state batteries are at least a decade away from commercial viability.", "SSB Decade Away"),
        ("Global internet penetration is below 30% of the world population.", "Internet Low"),
        ("Commercial space tourism is pure science fiction.", "Space Tourism SciFi"),
        ("Cryptocurrency has no legitimate use cases and will disappear.", "Crypto No Use"),
        ("Machine translation is fundamentally unreliable and unusable for real work.", "MT Unreliable"),
        ("Voice assistants like Alexa are a passing fad with limited utility.", "Voice Assistants Fad"),
        ("Remote work is impractical for most knowledge workers.", "Remote Impractical"),
        ("Drones are restricted to military use and hobbyist toys.", "Drones Military Only"),
        ("The Great Barrier Reef is healthy and not at risk from climate change.", "GBR Healthy"),
        ("Dark matter has been directly detected in laboratory experiments.", "Dark Matter Detected"),
    ]

    for content, title in outdated_se:
        items.append(BenchmarkItem(content=content, title=title, labels=["outdated"],
                                   metadata={"domain": "se"}))
    for content, title in outdated_general:
        items.append(BenchmarkItem(content=content, title=title, labels=["outdated"],
                                   metadata={"domain": "general"}))

    # --- Deprecated items (40) ---
    deprecated = [
        ("Use Python 2.7 with print statements for all new development projects.", "Python 2.7", "se"),
        ("jQuery is essential for any web application to handle DOM manipulation and AJAX.", "jQuery Essential", "se"),
        ("CoffeeScript compiles to JavaScript and is the best way to write clean JS code.", "CoffeeScript", "se"),
        ("Use Bower to manage front-end package dependencies in your project.", "Bower", "se"),
        ("Grunt task runner should be used for automating build processes.", "Grunt", "se"),
        ("Flash Player is required for rich multimedia content on the web.", "Flash Player", "se"),
        ("Use FTP to deploy your application files to the production server.", "FTP Deploy", "se"),
        ("Internet Explorer 6 compatibility is essential for enterprise web applications.", "IE6 Compat", "se"),
        ("SVN (Subversion) is the industry standard for version control.", "SVN Standard", "se"),
        ("Use XML-RPC for all service-to-service communication.", "XML-RPC", "se"),
        ("CGI scripts in Perl are the standard for web application backends.", "CGI Perl", "se"),
        ("Use table-based layouts for cross-browser compatible web design.", "Table Layouts", "se"),
        ("SOAP with WSDL is the proper way to build web service APIs.", "SOAP WSDL", "se"),
        ("Use CVS (Concurrent Versions System) for source code management.", "CVS", "se"),
        ("Silverlight is the recommended platform for rich internet applications.", "Silverlight", "se"),
        ("Use Mercurial (hg) as your distributed version control system.", "Mercurial", "se"),
        ("Prototype.js provides essential JavaScript utilities that the language lacks.", "Prototype.js", "se"),
        ("Use Dreamweaver for professional web development.", "Dreamweaver", "se"),
        ("Java applets provide rich interactive content in web browsers.", "Java Applets", "se"),
        ("Use Microsoft Access as your production database.", "MS Access Production", "se"),
        ("Write inline SQL queries directly in your PHP application code.", "Inline SQL PHP", "se"),
        ("Use iframes extensively to compose your web application from multiple pages.", "iframes", "se"),
        ("Windows Server 2003 is the recommended platform for .NET applications.", "Windows Server 2003", "se"),
        ("Use MD5 for hashing passwords in your authentication system.", "MD5 Passwords", "se"),
        ("Store user sessions in global variables on the application server.", "Global Sessions", "se"),
        ("Use synchronous XMLHttpRequest calls for server communication.", "Sync XHR", "se"),
        ("Develop mobile apps using PhoneGap/Apache Cordova for maximum compatibility.", "PhoneGap", "se"),
        ("Use SourceSafe for team-based version control in Visual Studio.", "SourceSafe", "se"),
        ("Use leaded gasoline for better engine performance.", "Leaded Gasoline", "general"),
        ("Asbestos is an excellent building insulation material.", "Asbestos Insulation", "general"),
        ("Mercury thermometers are the gold standard for temperature measurement.", "Mercury Thermometers", "general"),
        ("CFCs are effective and safe refrigerants for air conditioning systems.", "CFCs", "general"),
        ("Bloodletting is an effective treatment for fever and infection.", "Bloodletting", "general"),
        ("Use DDT for mosquito control in residential areas.", "DDT", "general"),
        ("Thalidomide is a safe treatment for morning sickness during pregnancy.", "Thalidomide", "general"),
        ("Cigarette smoking has no proven link to lung cancer.", "Smoking Safe", "general"),
        ("The food pyramid with bread at the base is the optimal diet guide.", "Food Pyramid", "general"),
        ("Use X-ray shoe-fitting machines to ensure proper shoe fit.", "X-Ray Shoe Fitting", "general"),
        ("Trans fats are a healthy alternative to saturated fats.", "Trans Fats Healthy", "general"),
        ("Lobotomy is an effective treatment for mental illness.", "Lobotomy", "general"),
    ]

    for content, title, domain in deprecated:
        items.append(BenchmarkItem(content=content, title=title, labels=["deprecated"],
                                   metadata={"domain": domain}))

    return items


# ── T4: Evidence Grounding ────────────────────────────────────────────────


@dataclass
class GroundingItem:
    """A claim with KB context for evidence grounding."""
    claim: str
    context: list[str]  # KB chunks as context
    label: str  # supported, unsupported, partial
    metadata: dict = field(default_factory=dict)


def t4_evidence_grounding_dataset() -> list[GroundingItem]:
    """Generate evidence grounding dataset for T4.

    Labels: supported, unsupported, partial.
    """
    items = []

    # --- Supported claims ---
    supported = [
        ("Python uses reference counting as its primary garbage collection mechanism.",
         ["Python employs automatic memory management. Its primary mechanism is reference counting, where each object maintains a count of references pointing to it. When the count reaches zero, the memory is freed. Python also has a cycle detector for handling circular references."],
         {"domain": "se", "topic": "python_gc"}),

        ("Docker containers share the host operating system kernel.",
         ["Docker uses OS-level virtualization. Unlike virtual machines that run a full OS, Docker containers share the host system's kernel. This makes them significantly lighter and faster to start than VMs.", "Containers isolate processes using Linux namespaces and cgroups while sharing the underlying kernel."],
         {"domain": "se", "topic": "docker"}),

        ("B-trees are commonly used in database indexes for efficient range queries.",
         ["Database systems typically use B-tree or B+ tree indexes for organizing data on disk. B-trees maintain sorted data and provide O(log n) time for search, insert, and delete operations. They are particularly well-suited for range queries because adjacent keys are stored in nearby disk blocks."],
         {"domain": "se", "topic": "btree"}),

        ("The speed of light is approximately 300,000 km/s.",
         ["The speed of light in vacuum, denoted c, is exactly 299,792,458 metres per second. This is a fundamental constant of nature and represents the maximum speed at which information or matter can travel."],
         {"domain": "general", "topic": "speed_of_light"}),

        ("TCP uses a three-way handshake to establish connections.",
         ["TCP connection establishment uses a three-way handshake: SYN, SYN-ACK, ACK. The client sends a SYN packet, the server responds with SYN-ACK, and the client confirms with ACK. This ensures both sides are ready for data transfer."],
         {"domain": "se", "topic": "tcp"}),

        ("React uses a virtual DOM to optimize rendering performance.",
         ["React maintains an in-memory representation of the UI called the virtual DOM. When state changes, React creates a new virtual DOM tree, diffs it against the previous one, and applies only the necessary changes to the real DOM. This reconciliation process minimizes expensive DOM operations."],
         {"domain": "se", "topic": "react"}),

        ("DNA has a double helix structure.",
         ["Deoxyribonucleic acid (DNA) is a molecule that carries genetic instructions. Watson and Crick described its structure as a double helix in 1953, with two strands of nucleotides wound around each other. The strands are held together by hydrogen bonds between complementary base pairs."],
         {"domain": "general", "topic": "dna"}),

        ("Git stores snapshots of the entire project, not diffs between versions.",
         ["Unlike other version control systems that store delta changes, Git takes a snapshot of all files at each commit. If a file hasn't changed, Git stores a reference to the previous identical file rather than a new copy. This snapshot-based approach is key to Git's branching and merging capabilities."],
         {"domain": "se", "topic": "git_storage"}),
    ]

    for claim, context, meta in supported:
        items.append(GroundingItem(claim=claim, context=context, label="supported", metadata=meta))

    # --- Unsupported claims ---
    unsupported = [
        ("Python 4.0 was released in 2025 with a completely new syntax.",
         ["Python 3.12 was released in October 2023 with improved error messages and type parameter syntax. Python follows a yearly release cycle with minor version increments.", "The Python Steering Council has stated there are no plans for Python 4.0."],
         {"domain": "se", "topic": "python_version"}),

        ("Kubernetes automatically fixes all application bugs through self-healing.",
         ["Kubernetes provides self-healing capabilities for infrastructure: it restarts failed containers, replaces unresponsive pods, and reschedules workloads when nodes die. It uses health checks (liveness and readiness probes) to detect failures."],
         {"domain": "se", "topic": "k8s_healing"}),

        ("SQL databases cannot handle more than 1 million rows efficiently.",
         ["Modern relational databases like PostgreSQL can handle billions of rows with proper indexing. PostgreSQL supports partitioning for large tables, parallel query execution, and various index types including B-tree, GIN, and GiST."],
         {"domain": "se", "topic": "sql_scale"}),

        ("Einstein discovered quantum mechanics.",
         ["Quantum mechanics was developed by several physicists including Max Planck, Niels Bohr, Werner Heisenberg, and Erwin Schrodinger. Einstein contributed to quantum theory through his work on the photoelectric effect but was famously skeptical of quantum mechanics' implications."],
         {"domain": "general", "topic": "quantum_history"}),

        ("Redis stores all data exclusively on disk for durability.",
         ["Redis is an in-memory data structure store. While it supports persistence through RDB snapshots and AOF logging, its primary storage is in RAM. This is what gives Redis its exceptional speed for read and write operations."],
         {"domain": "se", "topic": "redis_storage"}),

        ("GraphQL replaces databases entirely.",
         ["GraphQL is a query language and runtime for APIs. It sits between clients and data sources, allowing clients to request exactly the data they need. GraphQL servers connect to various backends including databases, REST APIs, and microservices."],
         {"domain": "se", "topic": "graphql_role"}),

        ("The human body has 300 bones.",
         ["An adult human body typically has 206 bones. Babies are born with about 270 bones, some of which fuse together during growth. The skeletal system provides structure, protects organs, and enables movement."],
         {"domain": "general", "topic": "human_bones"}),

        ("TCP is connectionless and does not guarantee delivery.",
         ["TCP (Transmission Control Protocol) is a connection-oriented protocol. It establishes a connection through a three-way handshake and guarantees reliable, ordered delivery of data through sequence numbers, acknowledgments, and retransmission of lost packets."],
         {"domain": "se", "topic": "tcp_reliable"}),
    ]

    for claim, context, meta in unsupported:
        items.append(GroundingItem(claim=claim, context=context, label="unsupported", metadata=meta))

    # --- Partially supported claims ---
    # These claims contain a kernel of truth but overstate, oversimplify, or miss caveats.
    # The pattern: claim makes an absolute statement, context confirms the direction but adds nuance.
    partial = [
        ("React Server Components eliminate the need for any client-side JavaScript.",
         ["React Server Components (RSC) allow components to render on the server, reducing the JavaScript sent to the client. However, interactive components still require client-side JavaScript. RSC works alongside client components to provide the optimal mix of server and client rendering."],
         {"domain": "se", "topic": "rsc", "pattern": "overstates_scope"}),

        ("Microservices are always better than monoliths for scalability.",
         ["Microservices architecture allows independent scaling of individual services. However, it introduces complexity in networking, data consistency, and operational overhead. For smaller teams, a well-designed monolith can be more productive and easier to scale vertically."],
         {"domain": "se", "topic": "microservices_vs_monolith", "pattern": "false_absolute"}),

        ("NoSQL databases do not support transactions.",
         ["Many NoSQL databases now support transactions. MongoDB added multi-document ACID transactions in version 4.0. However, the scope and guarantees of transactions vary significantly between NoSQL systems, and some like Cassandra trade consistency for availability."],
         {"domain": "se", "topic": "nosql_transactions", "pattern": "outdated_claim"}),

        ("Machine learning can predict any outcome with enough data.",
         ["Machine learning can find patterns in data and make predictions. However, some systems are inherently unpredictable (chaotic systems). ML is also limited by data quality, model architecture, and the bias-variance tradeoff. It works best when there are learnable patterns in the training data."],
         {"domain": "general", "topic": "ml_limits", "pattern": "overstates_capability"}),

        ("Rust prevents all memory-related bugs.",
         ["Rust's ownership system and borrow checker prevent many common memory bugs including use-after-free, double free, and data races. However, Rust does allow unsafe code blocks where these guarantees are relaxed. Logic errors and certain memory leaks (via Rc cycles) are still possible."],
         {"domain": "se", "topic": "rust_safety", "pattern": "ignores_exceptions"}),

        ("CRISPR can edit any gene with perfect precision.",
         ["CRISPR-Cas9 enables targeted gene editing with relatively high precision. However, off-target effects remain a concern, and efficiency varies depending on the target site. Recent improvements like base editing and prime editing have increased precision, but perfect accuracy is not guaranteed."],
         {"domain": "general", "topic": "crispr_precision", "pattern": "overstates_precision"}),

        ("Kubernetes replaces the need for any infrastructure management.",
         ["Kubernetes automates container orchestration, scaling, and deployment. However, clusters themselves require infrastructure management: node provisioning, networking, storage, security patches, and cluster upgrades. Managed services like EKS and GKE reduce but don't eliminate this overhead."],
         {"domain": "se", "topic": "k8s_ops", "pattern": "overstates_scope"}),

        ("WebAssembly runs at native speed in browsers.",
         ["WebAssembly provides near-native performance in browsers, typically achieving 80-95% of native speed. The actual performance depends on the workload, browser implementation, and optimization. Some overhead exists from the browser sandbox and JavaScript interop."],
         {"domain": "se", "topic": "wasm_speed", "pattern": "exaggerates_performance"}),

        ("Docker containers are completely isolated from each other and the host.",
         ["Docker containers provide process-level isolation using Linux namespaces and cgroups. However, they share the host kernel, which means a kernel vulnerability can affect all containers. For stronger isolation, technologies like gVisor or Kata Containers add an additional security boundary."],
         {"domain": "se", "topic": "docker_isolation", "pattern": "overstates_isolation"}),

        ("Python is the fastest programming language for data science workloads.",
         ["Python is the most popular language for data science due to its extensive library ecosystem (NumPy, pandas, scikit-learn). However, Python itself is relatively slow; performance-critical operations are typically delegated to C/C++ extensions. Languages like Julia and Rust can outperform Python for compute-heavy tasks."],
         {"domain": "se", "topic": "python_speed", "pattern": "conflates_popularity_with_speed"}),

        ("Quantum computers can solve any problem exponentially faster than classical computers.",
         ["Quantum computers provide exponential speedup for specific problem classes, notably factoring (Shor's algorithm) and unstructured search (Grover's algorithm provides quadratic, not exponential, speedup). For many practical problems, quantum computers offer no advantage over classical algorithms."],
         {"domain": "general", "topic": "quantum_speedup", "pattern": "overgeneralizes"}),

        ("Agile methodology eliminates the need for upfront planning and documentation.",
         ["Agile methodologies like Scrum and Kanban emphasize iterative development and responding to change. However, Agile does not eliminate planning; it replaces big upfront design with continuous planning in shorter cycles. Documentation is valued when useful, following the principle 'working software over comprehensive documentation' (not 'no documentation')."],
         {"domain": "se", "topic": "agile_planning", "pattern": "misinterprets_principle"}),
    ]

    for claim, context, meta in partial:
        items.append(GroundingItem(claim=claim, context=context, label="partial", metadata=meta))

    return items


# ── KQAB Suite Builder ────────────────────────────────────────────────────


def build_kqab_suite(variant: str = "synth") -> dict[str, KQABTask]:
    """Build the KQAB benchmark suite (T1-T4).

    Args:
        variant: Dataset variant to use:
            - "synth": Synthetic datasets only (original KQAB)
            - "public": Public datasets (MNLI for T2, FEVER for T4) + expanded synthetic (T1, T3)
            - "combined": Both synthetic and public datasets merged

    Returns:
        Dict mapping task ID to KQABTask.
    """
    from akm.benchmarks.datasets import immune_dataset

    # T1: Threat Detection (always uses immune dataset - our novel contribution)
    t1_items = immune_dataset()
    t1 = KQABTask(
        task_id="T1",
        name="Threat Detection",
        description="Classify KB chunks as healthy or one of 4 threat types",
        labels=["healthy", "hallucination", "staleness", "bias", "contradiction"],
        items=t1_items,
        domain="mixed",
    )

    # T2: Contradiction Discovery
    if variant in ("public", "combined"):
        from akm.benchmarks.public_datasets import load_mnli_for_t2, mnli_to_benchmark_items
        mnli_pairs = load_mnli_for_t2(n_per_class=67)
        t2_public_items = mnli_to_benchmark_items(mnli_pairs)

    if variant == "synth":
        t2_pairs = t2_contradiction_dataset()
        t2_items = [
            BenchmarkItem(
                content=f"CHUNK A: {p.chunk_a}\n\nCHUNK B: {p.chunk_b}",
                title=f"pair_{i}",
                labels=[p.label],
                metadata={**p.metadata, "chunk_a": p.chunk_a, "chunk_b": p.chunk_b},
            )
            for i, p in enumerate(t2_pairs)
        ]
    elif variant == "public":
        t2_items = t2_public_items
    else:  # combined
        t2_synth_pairs = t2_contradiction_dataset()
        t2_synth_items = [
            BenchmarkItem(
                content=f"CHUNK A: {p.chunk_a}\n\nCHUNK B: {p.chunk_b}",
                title=f"pair_{i}",
                labels=[p.label],
                metadata={**p.metadata, "chunk_a": p.chunk_a, "chunk_b": p.chunk_b},
            )
            for i, p in enumerate(t2_synth_pairs)
        ]
        t2_items = t2_synth_items + t2_public_items

    t2 = KQABTask(
        task_id="T2",
        name="Contradiction Discovery",
        description="Given a pair of KB chunks, classify as contradicts/consistent/unrelated",
        labels=["contradicts", "consistent", "unrelated"],
        items=t2_items,
        domain="mixed",
    )

    # T3: Temporal Decay (always synthetic - no public dataset exists)
    t3_items = t3_temporal_decay_dataset()
    t3 = KQABTask(
        task_id="T3",
        name="Temporal Decay Detection",
        description="Classify KB chunks as current/outdated/deprecated",
        labels=["current", "outdated", "deprecated"],
        items=t3_items,
        domain="mixed",
    )

    # T4: Evidence Grounding
    if variant in ("public", "combined"):
        from akm.benchmarks.public_datasets import load_fever_for_t4, fever_to_benchmark_items
        fever_items = load_fever_for_t4(n_per_class=67)
        t4_public_items = fever_to_benchmark_items(fever_items)

    if variant == "synth":
        t4_grounding = t4_evidence_grounding_dataset()
        t4_items = [
            BenchmarkItem(
                content=f"CLAIM: {g.claim}\n\nCONTEXT:\n" + "\n---\n".join(g.context),
                title=f"grounding_{i}",
                labels=[g.label],
                metadata={**g.metadata, "claim": g.claim, "context": g.context},
            )
            for i, g in enumerate(t4_grounding)
        ]
    elif variant == "public":
        t4_items = t4_public_items
    else:  # combined
        t4_synth = t4_evidence_grounding_dataset()
        t4_synth_items = [
            BenchmarkItem(
                content=f"CLAIM: {g.claim}\n\nCONTEXT:\n" + "\n---\n".join(g.context),
                title=f"grounding_{i}",
                labels=[g.label],
                metadata={**g.metadata, "claim": g.claim, "context": g.context},
            )
            for i, g in enumerate(t4_synth)
        ]
        t4_items = t4_synth_items + t4_public_items

    t4 = KQABTask(
        task_id="T4",
        name="Evidence Grounding",
        description="Given a claim and KB context, classify as supported/unsupported/partial",
        labels=["supported", "unsupported", "partial"],
        items=t4_items,
        domain="mixed",
    )

    return {"T1": t1, "T2": t2, "T3": t3, "T4": t4}


def kqab_summary(suite: dict[str, KQABTask]) -> dict:
    """Summary statistics for a KQAB suite."""
    total = sum(t.size for t in suite.values())
    return {
        "total_items": total,
        "tasks": {
            tid: {
                "name": task.name,
                "n_items": task.size,
                "labels": task.labels,
                "label_distribution": {
                    label: sum(1 for item in task.items if item.labels[0] == label)
                    for label in task.labels
                },
            }
            for tid, task in suite.items()
        },
    }
