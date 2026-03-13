with open("docker-compose.yml", "r", encoding="utf-8") as f:
    lines = f.readlines()
    
out = []
for line in lines:
    if line.startswith("networks:"):
        break
    if "pinchtab" not in line and "volumes:" not in line:
         out.append(line)
         
# Filter previous bad logic
out = [line for line in lines if not line.startswith("volumes:") and not "pinchtab" in line and not line.startswith("networks:") and not "gc-network:" in line and not "driver: bridge" in line and not "warp-data:" in line]

out.append("""  # ---------------------------------------------------------------
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

networks:
  gc-network:
    driver: bridge

volumes:
  warp-data:
  pinchtab-data:
""")

with open("docker-compose.yml", "w", encoding="utf-8") as f:
    f.writelines(out)