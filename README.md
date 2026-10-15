# CampusHub: Campus Event & Resource Management Platform

Multi-container application (frontend, 5 backend services, Postgres) built with Docker and deployed on
**Microsoft Azure** (Container Apps) and **AWS** (ECS Fargate) for a cloud comparison project 

Colleges run hackathons, workshops, seminars and webinars. Registration, event management, resource
allocation and notifications depend on each other, so each one is its own containerised service.

## Architecture

| Container              | Role                                                                        |
|------------------------|-----------------------------------------------------------------------------|
| `frontend` (nginx)     | Single-page UI (student and admin) and reverse proxy to the services        |
| `auth-service`         | Register, login (hashed passwords), signed token                            |
| `event-service`        | Events: admins create/delete, everyone lists                                |
| `registration-service` | Students register/cancel, admins see attendees, `/api/stress` load endpoint |
| `resource-service`     | Resources and allocating them to events                                     |
| `notification-service` | Stores and lists per-user notifications                                     |
| `db` (Postgres 16)     | users, events, registrations, resources, allocations, notifications         |

Every backend listens on **port 8000** and has `GET /health`. The frontend listens on port 80.
Services call each other by name (e.g. `http://event-service:8000`).

## Run locally (everyone does this first)

Requirements: Docker Desktop (running) and Git.

```
git clone https://github.com/23z272/campus-platform.git
cd campus-platform
docker compose up --build
```
Open http://localhost:8080

Stop with `Ctrl+C`, then `docker compose down`.
If you ever change `db/init.sql`, reset the database with `docker compose down -v` before starting again.

### Test checklist
1. Register an **Admin** (access code `admin123`), create an event, add a resource and allocate it to the event.
2. Log out, register a **Student**, register for the event.
3. Check *My registrations* and *Notifications* (student), then *Attendees & allocations* (admin).

## Accounts
- **Student:** Student tab, Register, then Login.
- **Admin:** Admin tab, Register with the access code (`ADMIN_CODE`, default `admin123`).
- Passwords are stored hashed (pbkdf2-sha256) in `users`. Login returns a signed token valid for 8 hours.

## Environment variables

| Service              | Variables                                                                                    |
|----------------------|----------------------------------------------------------------------------------------------|
| all backends         | `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `JWT_SECRET` (**same value everywhere**)     |
| auth-service         | `ADMIN_CODE`                                                                                 |
| registration-service | `EVENT_SERVICE_URL`, `NOTIFICATION_SERVICE_URL`                                              |
| frontend             | `AUTH_URL`, `EVENT_URL`, `REGISTRATION_URL`, `RESOURCE_URL`, `NOTIFICATION_URL`              |
| db                   | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`                                          |

In the cloud, set the URLs to the internal service names, for example `EVENT_URL=http://event-service`
(Azure Container Apps internal ingress) or the ECS service-discovery / internal load balancer name on AWS.
Put `DB_PASSWORD`, `JWT_SECRET` and `ADMIN_CODE` in cloud secrets, not in plain text.

## Team workflow

1. Clone the repo and run it locally. Do not start cloud work until `docker compose up` works for you.
2. Do **not** rename services, ports (8000) or `/api/...` paths. The frontend, nginx config and
   service-to-service calls depend on them. If something must change, tell the team first.
3. Use branches for changes: `git checkout -b my-change`, push, and open a pull request.
   Pull the latest main before you start: `git pull`.
4. Both clouds deploy the **same images from the same commit**, so the comparison is fair.

## Cloud tasks

### Azure team (A1, A2)
- **A1 (deployment lead):** `az login`, create the Resource Group and Azure Container Registry (ACR),
  build, tag and push the frontend, resource and notification images, deploy those Container Apps,
  test the public URL, record screenshots and notes.
- **A2 (operations lead):** create the Log Analytics workspace and Container Apps Environment,
  push/deploy the auth, event, registration and db apps, set ingress (frontend external, the rest internal),
  set scaling rules (min/max replicas), test registration and DB records, check Azure Monitor logs and metrics.

Image push example (replace `<acr>`):
```
az acr login --name <acr>
docker build -t <acr>.azurecr.io/campus-event-service:v1 ./event-service
docker push <acr>.azurecr.io/campus-event-service:v1
```
Repeat for `frontend`, `auth-service`, `registration-service`, `resource-service`, `notification-service` and `db`.

### AWS team (B1, B2)
- **B1 (deployment lead):** IAM user/role and `aws configure`, one ECR repository per service, push all images,
  ECS Fargate cluster, task definitions and services for frontend, resource and notification, test the ALB URL.
- **B2 (networking and operations lead):** VPC, subnets, security groups, Application Load Balancer for the frontend,
  task definitions for auth, event, registration and db, auto scaling policies, CloudWatch logs (awslogs driver) and metrics.

Notes for both clouds:
- Build images for `linux/amd64` (on Apple Silicon: `docker build --platform linux/amd64 ...`).
- The db container needs persistent storage (Azure Files / EFS) or use a managed Postgres service.
- Only the frontend gets public access. Everything else stays internal.

## Cloud demo ideas (what makes it a cloud project)
- **Horizontal scaling:** set a scaling rule on `registration-service` and run a load test against
  `/api/stress?ms=200` while watching replicas increase, then decrease after the load stops.
- **Vertical scaling:** change CPU/memory per replica and repeat the same load test.
- **Monitoring:** logs, CPU/memory, request count, replica count and an alert (Azure Monitor / CloudWatch).
- **Resilience:** use `/health` for health probes, stop a container and show it restart.

## Comparison metrics (Azure vs AWS)
Use the same container sizes, region (or nearest equivalent) and the same load test on both clouds.
- Setup time and number of steps
- Time to scale up and down, and max replicas reached
- Response time and error rate under load
- CPU and memory usage
- Monitoring and logging ease
- Cost during the test
- Overall difficulty (with notes and screenshots)

## After the demo
**Delete all cloud resources** to avoid charges (Azure: delete the Resource Group; AWS: delete ECS services, cluster,
ALB, NAT gateways, ECR repositories, log groups and the VPC).