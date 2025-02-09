# Solar Fleet Monitoring Dashboard

![Dashboard Screenshot](https://github.com/user-attachments/assets/22b17fd1-0431-4813-90ca-c010ec9318f9)

A **Streamlit** dashboard for monitoring your solar fleet in real time. This project leverages intelligent caching, multiple solar API integrations, and even Selenium-based web scraping to ensure you always have the latest data while minimizing API costs.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [API Support Details](#api-support-details)
- [Future Enhancements](#future-enhancements)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Overview

This dashboard is built with [Streamlit](https://streamlit.io/), a powerful yet simple UI framework for Python. It provides a centralized view for solar fleet monitoring by:

- **Caching API calls:** Dynamically caching responses from 1 hour to 1 month based on data change frequency to reduce unnecessary hits on production servers.
- **Integrating multiple APIs:** Currently supporting SolarEdge v2, Enphase v4 (partner API, nearly complete), and Sol-Ark via Selenium & web scraping, with more integrations on the way.
- **Flexible Data Retrieval:** Using Selenium to scrape data from web pages when no API is available.

---

## Features

- **Intelligent Caching:**
  - Automatically caches expensive API calls for durations ranging from one hour to one month.
  - Minimizes costs by reducing redundant calls to production servers during frequent code changes.
  
- **Multi-Source Data Integration:**
  - **SolarEdge v2 API:** Fully functional integration.
  - **Enphase v4 (Partner) API:** Integration is nearly complete.
  - **Sol-Ark:** Data extraction via Selenium (battery data is available; alerts are in progress).
  - Planned support for **Sonnen, SMA, AP-Smart**, and others.

- **Dynamic UI with Streamlit:**
  - Rapidly build interactive dashboards for data-centric projects.
  - Easily extendable and modifiable to suit different solar monitoring requirements.

---

## Installation

### Prerequisites

- Python 3.x
- [Streamlit](https://streamlit.io/)
- [Selenium](https://www.selenium.dev/) (only if using web scraping)
- Additional dependencies as listed in `requirements.txt`

### Setup Steps

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/solar-fleet-dashboard.git
   cd solar-fleet-dashboard


2. **Clone the Repository:**

   ```bash
   pip install -r requirements.txt
   streamlit run Dashboard.py