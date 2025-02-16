from app.models import User, Ticker  # Import your searchable models


def register_commands(app):
    @app.cli.command()
    def reindex():
        """Reindex all searchable models."""
        # Get all models that inherit from SearchableMixin
        searchable_models = [User, Ticker]  # Add any other searchable models

        for model in searchable_models:
            try:
                print(f"Reindexing {model.__name__}...")
                model.reindex()
                print(f"Finished reindexing {model.__name__}")
            except Exception as e:
                print(f"Error reindexing {model.__name__}: {e}")