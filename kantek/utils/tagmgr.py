from typing import Optional, Union

from pyArango.document import DocumentStore
from telethon.events import NewMessage

from database.arango import ArangoDB
from utils.client import KantekClient

TagValue = Union[bool, str, int]
TagName = Union[int, str]


class TagManager:
    def __init__(self, event: NewMessage.Event):
        self._client: KantekClient = event.client
        self._db = self._client.db
        self.chat_id = event.chat_id
        self._collection = self._db.groups
        self._document = self._collection[self.chat_id]
        self._named_tags: DocumentStore = self._document['named_tags']
        self.named_tags = self._document['named_tags'].getStore()
        self.tags = self._document['tags']

    def get_tag(self, tag_name: TagName) -> Optional[TagValue]:
        """Get a Tags Value

        Args:
            tag_name: The name of the Tag

        Returns:
            The tags value for named tags
            True if the tag exists
            None if the Tag doesnt exist

        """
        return self.named_tags.get(tag_name, tag_name in self.tags or None)

    def __getitem__(self, item: TagName) -> TagValue:
        return self.get_tag(item)

    def set_tag(self, tag_name: TagName, value: Optional[TagValue] = None) -> None:
        """Set a tags value or create it.
        If value is None a normal tag will be created. If the value is not None a named tag with
         that value will be created
        Args:
            tag_name: Name of the Tag
            value: The value of the tag

        Returns: None

        """
        if value is None:
            if tag_name not in self.tags:
                self.tags.append(tag_name)
                self._document['tags'] = self.tags
        elif value is not None:
            self.named_tags[tag_name] = value
            self._document['named_tags'] = self.named_tags
        self._document.save()

    def __setitem__(self, key: TagName, value: TagValue) -> None:
        self.set_tag(key, value)

    def clear(self) -> None:
        """Clears all tags that a Chat has."""
        self._document['named_tags'] = {}
        self._document['tags'] = []
        self._document.save()
