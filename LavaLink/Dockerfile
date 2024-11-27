FROM openjdk:17-slim

WORKDIR /app

# Download Lavalink.jar
RUN apt-get update && \
    apt-get install -y wget && \
    wget https://github.com/lavalink-devs/Lavalink/releases/download/4.0.8/Lavalink.jar

COPY application.yml application.yml

CMD ["java", "-jar", "Lavalink.jar"]