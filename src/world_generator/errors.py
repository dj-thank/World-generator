class WorldGeneratorError(RuntimeError):
    """Base error for expected pipeline failures."""


class ConfigurationError(WorldGeneratorError):
    """Raised when credentials or executable configuration is missing."""


class ProviderError(WorldGeneratorError):
    """Raised when an image or video provider fails."""


class ReconstructionError(WorldGeneratorError):
    """Raised when camera solving or 3D reconstruction fails."""


class ExternalCommandError(ReconstructionError):
    """Raised when a required local executable exits unsuccessfully."""
