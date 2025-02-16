from flask import current_app
from elasticsearch.exceptions import NotFoundError


def create_index(index, model):
    """Create an index with ngram analyzer for partial matching"""
    if not current_app.elasticsearch:
        return

    # Get field names from the model's __searchable__
    fields = getattr(model, '__searchable__', [])
    field_mappings = {
        field: {
            "type": "text",
            "analyzer": "ngram_analyzer",
            "search_analyzer": "standard",
            "fields": {
                "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                }
            }
        } for field in fields
    }

    mapping = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "ngram_analyzer": {
                        "tokenizer": "ngram_tokenizer",
                        "filter": ["lowercase"]
                    }
                },
                "tokenizer": {
                    "ngram_tokenizer": {
                        "type": "ngram",
                        "min_gram": 3,
                        "max_gram": 4,  # Reduced from 10 to comply with max_ngram_diff
                        "token_chars": ["letter", "digit"]
                    }
                }
            },
            "index": {
                "max_ngram_diff": 1  # Explicitly set the limit
            }
        },
        "mappings": {
            "properties": field_mappings
        }
    }

    try:
        # Delete existing index if it exists
        if current_app.elasticsearch.indices.exists(index=index):
            current_app.elasticsearch.indices.delete(index=index)

        # Create new index with the mapping
        current_app.elasticsearch.indices.create(index=index, body=mapping)
    except Exception as e:
        print(f"Error creating index: {str(e)}")


def add_to_index(index, model):
    """Add a model to the search index"""
    if not current_app.elasticsearch:
        return

    payload = {}
    for field in model.__searchable__:
        payload[field] = getattr(model, field)

    try:
        current_app.elasticsearch.index(index=index, id=model.id, document=payload)
    except Exception as e:
        print(f"Error indexing document: {str(e)}")


def remove_from_index(index, model):
    """Remove a model from the search index"""
    if not current_app.elasticsearch:
        return

    try:
        current_app.elasticsearch.delete(index=index, id=model.id)
    except NotFoundError:
        pass  # Ignore if document wasn't found
    except Exception as e:
        print(f"Error removing document: {str(e)}")


def query_index(index, query, page, per_page):
    """Search the index with support for partial matching"""
    if not current_app.elasticsearch:
        return [], 0

    try:
        search = current_app.elasticsearch.search(
            index=index,
            body={
                "query": {
                    "bool": {
                        "should": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["*"],
                                    "fuzziness": "AUTO"
                                }
                            },
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["*"],
                                    "type": "phrase_prefix"
                                }
                            }
                        ]
                    }
                }
            },
            from_=(page - 1) * per_page,
            size=per_page
        )

        ids = [int(hit['_id']) for hit in search['hits']['hits']]
        return ids, search['hits']['total']['value']
    except Exception as e:
        print(f"Error performing search: {str(e)}")
        return [], 0


def reindex_all(index, model_class):
    """Reindex all instances of a model"""
    if not current_app.elasticsearch:
        return

    try:
        # First create/recreate the index with proper mappings
        create_index(index, model_class)

        # Then reindex all objects
        for obj in model_class.query.all():
            add_to_index(index, obj)
    except Exception as e:
        print(f"Error reindexing all documents: {str(e)}")
