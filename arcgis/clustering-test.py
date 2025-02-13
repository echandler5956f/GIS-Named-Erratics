import pandas as pd
import numpy as np
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sentence_transformers import SentenceTransformer
import umap.umap_ as umap
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
import folium

# Download NLTK resources
nltk.download('stopwords')
nltk.download('wordnet')

# Text preprocessing setup
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

def preprocess_text(text):
    if pd.isnull(text):
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    words = text.split()
    words = [lemmatizer.lemmatize(word) for word in words if word not in stop_words]
    return ' '.join(words)

# Load and prepare data
df = pd.read_csv('cluster-dummy-data.csv')  # Ensure columns: id, description, latitude, longitude
df['cleaned_description'] = df['description'].apply(preprocess_text)

# Generate embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(df['cleaned_description'].tolist(), show_progress_bar=True)

# Dimensionality reduction with UMAP
reducer = umap.UMAP(n_components=2, random_state=42)
reduced_embeddings = reducer.fit_transform(embeddings)

# Clustering with DBSCAN
clustering = DBSCAN(eps=0.875, min_samples=2)
df['cluster'] = clustering.fit_predict(reduced_embeddings)

# Analyze clusters using TF-IDF
def get_top_tfidf_terms(texts, n=10):
    tfidf = TfidfVectorizer(stop_words='english')
    tfidf_matrix = tfidf.fit_transform(texts)
    feature_names = tfidf.get_feature_names_out()
    scores = np.asarray(tfidf_matrix.mean(axis=0)).ravel()
    top_indices = scores.argsort()[::-1][:n]
    return [feature_names[i] for i in top_indices]

print("Cluster analysis:")
cluster_terms = {}
for cluster_id in df['cluster'].unique():
    cluster_texts = df[df['cluster'] == cluster_id]['cleaned_description']
    top_terms = get_top_tfidf_terms(cluster_texts)
    cluster_terms[cluster_id] = top_terms
    print(f"Cluster {cluster_id}: {', '.join(top_terms)}")

# Generate interactive map
def generate_cluster_map(dataframe):
    base_map = folium.Map(
        location=[dataframe['latitude'].mean(), dataframe['longitude'].mean()],
        zoom_start=5
    )
    
    # Color mapping for clusters
    colors = {
        -1: 'gray',
        0: 'blue',
        1: 'green',
        2: 'red',
        3: 'orange',
        4: 'purple',
        5: 'darkred',
        6: 'lightblue'
    }
    
    # Add markers for each erratic
    for _, row in dataframe.iterrows():
        cluster_id = row['cluster']
        color = colors.get(cluster_id, 'gray')
        
        popup_text = f"""
        <b>Cluster:</b> {cluster_id}<br>
        <b>Top Terms:</b> {', '.join(cluster_terms.get(cluster_id, []))}<br>
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

# Generate and save map
erratics_map = generate_cluster_map(df)
erratics_map.save('erratics_clusters_map.html')

print("Analysis complete. Map saved as 'erratics_clusters_map.html'")