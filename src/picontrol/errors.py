"""Exception hierarchy. / Hiérarchie des exceptions.

Two families matter at run time:
  * ReaderError - the NFC reader misbehaved; recoverable, the service re-initialises it.
  * TagError    - the tag *content* is unusable; retrying will not help.
Deux familles : ReaderError (lecteur NFC en défaut, récupérable) et TagError (contenu du tag inutilisable).
"""


class PicontrolError(Exception):
    """Base class for all Pi Control errors."""


class ConfigError(PicontrolError):
    """Invalid or unreadable configuration."""


class ReaderError(PicontrolError):
    """Communication problem with the PN532 reader (recoverable)."""


class TagError(PicontrolError):
    """The tag content cannot be used."""


class NotOurTag(TagError):
    """Blank, foreign or non-Pi-Control tag."""


class LaunchError(TagError):
    """The requested game cannot be launched (invalid name, missing ROM...)."""
