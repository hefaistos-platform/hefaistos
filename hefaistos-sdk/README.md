# HEFAISTOS - Detection Engineering Platform

[![Architecture](https://img.shields.io/badge/Architecture-Microservices-blue.svg)](docker-compose.yml)
[![Backend-Framework](https://img.shields.io/badge/Backend-Django-green.svg)](backend/)
[![Frontend-Framework](https://img.shields.io/badge/Frontend-React-blue.svg)](frontend/)

HEFAISTOS is a multi-tenant, microservice-based platform for modern detection engineering and threat hunting. It is designed to be the central nervous system for a security team, enforcing a rigorous, collaborative, and data-driven workflow based on the `detection-tmpl` philosophy and advanced detection theory.

---

## 🚀 Core Features

* **Detection-as-Code:** Manages all detections in a version-controlled, tenant-aware repository.
* **Advanced Playbook Engine:** Implements the `detection-tmpl`, with structured fields for metadata, analytic robustness, framework mappings, and more.
* **Dynamic UI:** Frontend forms dynamically adapt to show fields relevant for "HUNT" vs. "DETECTION" playbooks.
* **Lifecycle Hub:** A Kanban board for visualizing the entire detection lifecycle, from "IDEA" to "DEPLOYED".
* **Collaborative Workflow:** A mandatory, API-driven peer review system before any detection can be approved.
* **Global Frameworks:** A central, admin-managed database for MITRE ATT&CK, D3FEND, and Engage techniques, importable via CSV/XLSX.
* **Coverage Mapping:** Integrates a static build of the ATT&CK Navigator to visualize deployed detection coverage, with a D3FEND overlay.
* **Plugin Architecture:** A decoupled, event-driven architecture using RabbitMQ and a Python SDK for building custom connectors.

---

## 🏛️ System Architecture

HEFAISTOS runs as a set of containerized services, managed by `docker-compose`.

* **`backend`**: The main Django/GraphQL API server. This is the "brain" of the platform, handling all business logic and authentication.
* **`frontend`**: The React (Sprint 0) themed single-page application that provides the user interface.
* **`db`**: The PostgreSQL database, which stores all metadata for playbooks, users, rules, etc.
* **`elasticsearch`**: Provides full-text search capabilities for detection rules.
* **`rabbitmq`**: The RabbitMQ message bus that decouples the `backend` from the `connectors`.

### Connectors (Microservices)

These are standalone Python services that use the `hefaistos-sdk` to perform specific, isolated tasks.

* **`deploy_connector`**: Listens for `playbook.deploy.testing` events and calls the API to change the playbook's status.
* **`notification_connector`**: Listens for `playbook.review.created` events and creates `Notification` objects for users.
* **`threat_intel_connector`**: Polls an external MISP instance on a timer and automatically creates "Hunt Idea" playbooks from new intel.

---

## 🛠️ Getting Started (Developer Setup)

These instructions are for a Linux-based server.

### 1. Prerequisites

* `git`
* `docker`
* `docker-compose`

### 2. Clone the Repository

You must create your first organization and user.
```
bash
git clone -b main https://github.com/hefaistos-platform/hefaistos.git
cd hefaistos
git pull origin main
```

### 3. Build & Start All Services

```
docker compose up --build -d
```

### 4. Create Your Super User

```
docker-compose exec backend bash
python manage.py shell
```

Inside the Django shell, run:
```
from organizations.models import Organization
from identity.models import CustomUser
# 1. Create your organization
org = Organization.objects.create(name="DCG420")
# 2. Create your user
user = CustomUser.objects.create_superuser(
    username='hunt3r', 
    password='<your_strong_password>', 
    email='admin@hefaistos.local'
)
user.organization = org
user.save()
print("Admin user 'hunt3r' created and assigned to 'DCG420'.")
exit()
```
### 5. (Required) Import MITRE Data
The platform is not usable until the global framework data is imported.

Place your raw MITRE CSVs (e.g., enterprise-attack-v19.0.xlsx - techniques.csv, d3fend.csv, Engage-Data-V1.0.xlsx - Activities.csv) into a directory on the server (e.g., /tmp/frameworks).

Run the custom import command:
```
docker-compose exec backend python manage.py import_frameworks /tmp/frameworks
```

### 6. Access Application

HEFAISTOS UI: http://<your-server-ip>:3000
Backend (API via NGINX): https://<your-server-ip>/graphql (or http://<your-server-ip>/graphql)
Django Admin: https://<your-server-ip>/admin
RabbitMQ UI: http://<your-server-ip>:15672

🐍 Building a New Connector


See the documentation in hefaistos-sdk/README.md for a "Hello World" example and instructions on using the BaseConnector and HefaistosApiClient.

### "Hello World" Example (A New Connector)

This example creates a connector that listens for `playbook.deploy.testing` and just logs the message.

**`my_new_connector.py`:**

import logging
from hefaistos_sdk.connector import BaseConnector

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class HelloWorldConnector(BaseConnector):
    """
    A simple connector that listens for deploy events and prints them.
    """
    
    def get_queue_bindings(self):
        """
        Tells the BaseConnector what to listen for.
        Returns a list of (queue_name, routing_key) tuples.
        """
        return [
            ('hello_world_queue', 'playbook.deploy.testing')
        ]
        
    def process_message(self, routing_key, payload):
        """
        This is your business logic. It's called for every message.
        The `self.api_client` is available here.
        """
        logger.info("--- HELLO WORLD RECEIVED A MESSAGE ---")
        logger.info(f"  Routing Key: {routing_key}")
        logger.info(f"  Payload: {payload}")
        
        # Example: Call the API
        playbook_id = payload.get('playbook_id')
        if playbook_id:
            data = self.api_client.get_playbook_title(playbook_id)
            logger.info(f"  Playbook Title: {data['playbook']['title']}")
            
        # Return True to ACK (acknowledge) the message and remove it.
        # Return False to NACK (re-queue) the message to try again.
        return True


if __name__ == '__main__':
    logger.info("--- Starting 'Hello World' Connector (SDK v1.0) ---")
    connector = HelloWorldConnector(service_name="HelloWorld")
    connector.start_consuming()
