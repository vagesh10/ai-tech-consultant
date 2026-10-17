from app.vector_store import rebuild_vector_index

if __name__ == "__main__":
    count = rebuild_vector_index()
    print(f"Indexed {count} active articles.")