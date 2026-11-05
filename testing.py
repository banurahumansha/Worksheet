import os
import requests

# -----------------------------
# Grade 1 Science Topics
# -----------------------------
topics = {
    "Life_Science": ["Animals", "Plants", "Human_Body", "Habitats", "Food_Chains"],
    "Physical_Science": ["Light", "Sound", "Forces", "Magnets", "Energy"],
    "Earth_Science": ["Weather", "Seasons", "Water_Cycle", "Rocks_and_Soil"]
}

# Base folder to save SVGs
base_folder = "grade1_svgs"
os.makedirs(base_folder, exist_ok=True)

# -----------------------------
# Function to download SVG from URL
# -----------------------------
def download_svg(url, save_path):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(response.content)
            print(f"Downloaded: {save_path}")
        else:
            print(f"Failed to download: {url}")
    except Exception as e:
        print(f"Error: {e}")

# -----------------------------
# Example: SVG Repo search URLs (replace with real URLs)
# -----------------------------
# NOTE: You'll need to fill in real SVG URLs for each topic. Some sites have APIs.
example_svgs = {
    "Animals": [
        "https://www.svgrepo.com/show/1045/cat.svg",
        "https://www.svgrepo.com/show/1046/dog.svg"
    ],
    "Plants": [
        "https://www.svgrepo.com/show/1158/tree.svg",
        "https://www.svgrepo.com/show/1159/flower.svg"
    ],
    "Human_Body": [
        "https://www.svgrepo.com/show/2012/heart.svg"
    ],
    "Habitats": [
        "https://www.svgrepo.com/show/1497/forest.svg"
    ],
    "Food_Chains": [
        "https://www.svgrepo.com/show/1542/fish.svg",
        "https://www.svgrepo.com/show/1543/bird.svg"
    ]
}

# -----------------------------
# Download loop
# -----------------------------
for subject, subject_topics in topics.items():
    subject_folder = os.path.join(base_folder, subject)
    os.makedirs(subject_folder, exist_ok=True)

    for topic in subject_topics:
        topic_folder = os.path.join(subject_folder, topic)
        os.makedirs(topic_folder, exist_ok=True)

        svg_urls = example_svgs.get(topic, [])
        for idx, url in enumerate(svg_urls):
            file_name = f"{topic}_{idx+1}.svg"
            save_path = os.path.join(topic_folder, file_name)
            download_svg(url, save_path)

print("✅ Grade 1 SVG download complete!")
