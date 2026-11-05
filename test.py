import requests

def openverse_proxy(query="mountains", limit=5):
    url = f"https://api.openverse.engineering/v1/images?q={query}&per_page={limit}&format=json"
    headers = {"User-Agent": "Mozilla/5.0"}  # Required to get proper response

    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return {"error": f"Openverse API returned status {resp.status_code}"}

        data = resp.json()
        images = []
        for img in data.get("results", []):
            image_url = img.get("thumbnail") or img.get("url")
            if not image_url:
                continue
            images.append({
                "url": image_url,
                "title": img.get("title", "Openverse"),
                "source": "Openverse"
            })

        return {"results": images}

    except Exception as e:
        return {"error": str(e)}

# Run test
print(openverse_proxy("sunset", 3))
