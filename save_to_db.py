import json
import time
import psycopg2
import requests

# Database Configuration
DB_CONFIG = {
    "dbname": "mydb",
    "user": "user1",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

# API URL for creating a new creator
CREATE_CREATOR_API_URL = "https://api.galvor.in/kafka/event"

# Function to connect to PostgreSQL
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

# Function to check if creator exists, else create one
def get_or_create_creator(handle):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SET search_path TO galvor")
    cursor.execute("SELECT id FROM creator WHERE handle = %s", (handle,))
    result = cursor.fetchone()

    if result:
        creator_id = result[0]
        print(f"✅ Found existing creator {handle} with ID: {creator_id}")
    else:
        print(f"🔄 Creating new creator: {handle}")
        token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6InVtZXNoIiwidXNlcmlkIjoiMSIsImV4cCI6MTczOTUxNDQxNH0.pL6LmUI6cXfZocOIOmdG2rjqp4ngBBkt7s27BT953R4"
        body = {
                
                "handle": handle,
                  "platform": "instagram", 
                  "type": "creator"
                
            }
        # response = requests.post(CREATE_CREATOR_API_URL,json=body,headers={"Authorization": "Bearer" + " "+ token})
        response = {"id":1}

        # if response.status_code == 200:
        if True:
            print(f"✅ Event sent for creator {handle}, waiting for Kafka event...")
            
            # Wait until creator ID is available
            while True:
                cursor.execute("SELECT id FROM creator WHERE handle = %s", (handle,))
                result = cursor.fetchone()
                if result:
                    creator_id = result[0]
                    print(f" Creator {handle} created with ID: {creator_id}")
                    break
                time.sleep(5)
        else:
            print(f"❌ Failed to create creator {handle}. API response: {response.text}")
            return None

    cursor.close()
    conn.close()
    return creator_id

def insert_post(post, creator_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SET search_path TO galvor")

    # Ensure `media_id` is provided in JSON, else raise an error
    media_id = post.get("media_id")
    if not media_id:
        print(f"❌ Error: `media_id` missing for post {post['key']}")
        return None

    views = post.get("views", 0)  
    likes = post.get("likes", 0)  
    media_type = post.get("media_type", "image") 
    hashtag = post.get("hashtag", None) 

    cursor.execute(
        """
        INSERT INTO insta_post_info (media_id, key, timestamp, caption, media_url, media_type, created_at, is_deleted, views, likes, hashtag)
        VALUES (
            %s, %s, %s, %s, %s, %s, NOW(), FALSE, %s, %s, %s
        )
        ON CONFLICT (media_id) 
        DO UPDATE SET
            timestamp = EXCLUDED.timestamp,
            caption = EXCLUDED.caption,
            media_url = EXCLUDED.media_url,
            media_type = EXCLUDED.media_type,
            views = EXCLUDED.views,
            likes = EXCLUDED.likes,
            hashtag = EXCLUDED.hashtag,
            is_deleted = FALSE
        RETURNING media_id;
        """,
        (media_id, post["key"], post["timestamp"], post["caption"], post["img_url"], media_type, views, likes, hashtag)
    )

    media_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    print(f"✅ Inserted/Updated post {post['key']} with media_id: {media_id}")
    return media_id




# Function to insert comments into `comments` table
def insert_comments(post, media_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SET search_path TO galvor")

    # Check if comments exist in the JSON data
    comments = post.get("comments", [])

    if not comments:
        print(f"⚠️ No comments found for media_id {media_id}, skipping...")
        return

    for comment in comments:
        cursor.execute(
            """
            INSERT INTO comments (media_id, author, comment, mentions, timestamp)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                media_id,
                comment["author"],
                comment["comment"],
                json.dumps(comment["mentions"]),  # Convert list to JSON format
                comment["timestamp"]
            )
        )

    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Inserted {len(comments)} comments for media_id {media_id}")


# Function to insert collaborators into `collab` table
def insert_collabs(post, media_id, creator_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SET search_path TO galvor")

    for collab in post["collaborators"]:
        collab_type = "collab" if "@" in collab else "tag"
        cursor.execute(
            """
            INSERT INTO collab (media_id, author_id, collaborator, collab_type)
            VALUES (%s, %s, %s, %s);
            """,
            (media_id, creator_id, collab, collab_type)
        )

    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Inserted {len(post['collaborators'])} collaborators for media_id {media_id}")

# Main function to process JSON file
def process_posts(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        posts = json.load(file)

    for post in posts:
        handle = post["key"].split("/")[3]  
        creator_id = get_or_create_creator(handle)

        if creator_id:
            media_id = insert_post(post, creator_id)
            insert_comments(post, media_id)
            insert_collabs(post, media_id, creator_id)

if __name__ == "__main__":
    process_posts("out_sample.json")
