with open("docker-compose.yml", "r", encoding="utf-8") as f:
    text = f.read()

# We just want to insert the pinchtab service before networks:
pinchtab_service = """  # ---------------------------------------------------------------
  # PinchTab (Headless browser automation via HTTP)
  # ---------------------------------------------------------------
  pinchtab:
    image: pinchtab/pinchtab:latest
    container_name: gc-pinchtab
    restart: unless-stopped
    ports:
      - "9867:9867"
    volumes:
      - pinchtab-data:/data
    shm_size: '2gb'
    networks:
      - gc-network

networks:"""

text = text.replace("networks:", pinchtab_service)
text += "  pinchtab-data:\n"

with open("docker-compose.yml", "w", encoding="utf-8") as f:
    f.write(text)