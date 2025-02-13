import pandas as pd
import numpy as np
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sentence_transformers import SentenceTransformer
import hdbscan
from sklearn.feature_extraction.text import TfidfVectorizer
import folium

# Download NLTK resources if not already done
nltk.download('stopwords')
nltk.download('wordnet')

# Text preprocessing setup
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

def preprocess_text(text):
    """Lowercase, remove punctuation, remove stopwords, and lemmatize."""
    if pd.isnull(text):
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    words = text.split()
    words = [lemmatizer.lemmatize(word) for word in words if word not in stop_words]
    return ' '.join(words)

# 1) Load Data
df = pd.read_csv('arcgis/cluster-dummy-data.csv')  # Ensure columns: id, description, latitude, longitude

# 2) Clean Descriptions
df['cleaned_description'] = df['description'].apply(preprocess_text)

# 3) Generate Sentence Embeddings (No Dimensionality Reduction)
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(df['cleaned_description'].tolist(), show_progress_bar=True)

# 4) Clustering with HDBSCAN (operates on original embeddings)
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=2,   # Minimum number of points to form a cluster
    min_samples=2,        # How conservative you want the clustering
    metric='euclidean'    # Metric for distance
)
df['cluster'] = clusterer.fit_predict(embeddings)

# 5) Analyze Clusters with TF-IDF
def get_top_tfidf_terms(texts, n=10):
    tfidf = TfidfVectorizer(stop_words='english')
    tfidf_matrix = tfidf.fit_transform(texts)
    feature_names = tfidf.get_feature_names_out()
    scores = np.asarray(tfidf_matrix.mean(axis=0)).ravel()
    top_indices = scores.argsort()[::-1][:n]
    return [feature_names[i] for i in top_indices]

print("Cluster Analysis:")
cluster_terms = {}
for cluster_id in sorted(df['cluster'].unique()):
    cluster_texts = df[df['cluster'] == cluster_id]['cleaned_description']
    if len(cluster_texts) == 0:
        continue
    top_terms = get_top_tfidf_terms(cluster_texts)
    cluster_terms[cluster_id] = top_terms
    print(f"Cluster {cluster_id} => {', '.join(top_terms)}")

# 6) Generate Interactive Map
def generate_cluster_map(dataframe):
    # Center map on mean lat/long
    base_map = folium.Map(
        location=[dataframe['latitude'].mean(), dataframe['longitude'].mean()],
        zoom_start=5
    )
    
    # A small color palette for cluster IDs
    color_palette = [
        'blue', 'green', 'red', 'orange', 'purple',
        'darkred', 'lightblue', 'cadetblue', 'pink', 'black'
    ]
    
    # Assign colors to each unique cluster, with fallback for outliers
    unique_clusters = sorted(dataframe['cluster'].unique())
    cluster_color_map = {}
    
    for i, c_id in enumerate(unique_clusters):
        # Outliers in HDBSCAN are also labeled -1
        if c_id == -1:
            cluster_color_map[c_id] = 'gray'
        else:
            # Cycle through color palette
            cluster_color_map[c_id] = color_palette[i % len(color_palette)]
    
    # Add markers for each erratic
    for _, row in dataframe.iterrows():
        c_id = row['cluster']
        color = cluster_color_map.get(c_id, 'gray')
        popup_text = f"""
        <b>Cluster:</b> {c_id}<br>
        <b>Top Terms:</b> {', '.join(cluster_terms.get(c_id, []))}<br>
        <b>Description:</b> {row['description']}
        """
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=5,
            color=color,
            fill=True,
            fill_color=color,
            popup=folium.Popup(popup_text, max_width=300)
        ).add_to(base_map)
    
    return base_map

erratics_map = generate_cluster_map(df)
erratics_map.save('erratics_clusters_map_hdbscan.html')
print("Clustering complete. Map saved as 'erratics_clusters_map_hdbscan.html'")