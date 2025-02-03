from abc import ABC, abstractmethod

class SolarPlatform(ABC):
    @abstractmethod
    def get_sites(self):
        pass

    @abstractmethod
    def get_batteries_soc(self, site_id):
        pass

    @abstractmethod
    def get_alerts(self, site_id):
        pass
    