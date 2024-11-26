# Use Python 3.10 as the base image
FROM python:3.10-slim

COPY ./requirements.txt /app/requirements.txt

# Set the working directory
WORKDIR /app

# Install required Python packages
RUN pip install -r requirements.txt

# Copy the current directory contents into the container
COPY . .

# Expose port 5001
EXPOSE 5001

# Command to run the application
CMD ["python3", "app.py"]
