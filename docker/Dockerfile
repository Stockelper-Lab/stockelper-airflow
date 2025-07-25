# Use official Airflow image as base
FROM apache/airflow:2.7.1-python3.11

# Switch to root user to install system dependencies
USER root

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver - using fixed version for compatibility
RUN CHROME_DRIVER_VERSION="114.0.5735.90" \
    && wget -q "https://chromedriver.storage.googleapis.com/${CHROME_DRIVER_VERSION}/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip -d /usr/local/bin/ \
    && rm chromedriver_linux64.zip \
    && chmod +x /usr/local/bin/chromedriver

# Switch back to airflow user
USER airflow

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy DAGs and modules
COPY dags/ /opt/airflow/dags/
COPY modules/ /opt/airflow/dags/modules/
COPY config/airflow.cfg /opt/airflow/airflow.cfg

# Set environment variables
ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags
ENV AIRFLOW__CORE__PLUGINS_FOLDER=/opt/airflow/plugins
ENV AIRFLOW__CORE__BASE_LOG_FOLDER=/opt/airflow/logs
ENV AIRFLOW__CORE__LOGGING_LEVEL=INFO
ENV AIRFLOW__CORE__EXECUTOR=SequentialExecutor
ENV AIRFLOW__CORE__LOAD_EXAMPLES=False
ENV AIRFLOW__CORE__DEFAULT_TIMEZONE=UTC
ENV AIRFLOW__WEBSERVER__WEB_SERVER_PORT=8080
ENV AIRFLOW__WEBSERVER__BASE_URL=http://localhost:8080
ENV AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////opt/airflow/airflow.db

# Create necessary directories
RUN mkdir -p /opt/airflow/logs /opt/airflow/plugins

# Expose Airflow webserver port
EXPOSE 8080

# Default command
CMD ["airflow", "webserver"]
