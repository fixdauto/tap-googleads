"""GoogleAds tap class."""

from typing import List

from singer_sdk import Tap, Stream
from singer_sdk import typing as th  # JSON schema typing helpers

from tap_googleads.streams import (
    CampaignsStream,
    AdGroupsStream,
    AdGroupsPerformance,
    AdGroupsHourlyPerformance,
    AccessibleCustomers,
    CustomerHierarchyStream,
    CampaignPerformance,
    CampaignHourlyPerformance,
    CampaignPerformanceByAgeRangeAndDevice,
    CampaignPerformanceByGenderAndDevice,
    CampaignPerformanceByLocation,
    GeotargetsStream,
    GeoPerformance,
)

STREAM_TYPES = [
    CampaignsStream,
    AdGroupsStream,
    AdGroupsPerformance,
    AdGroupsHourlyPerformance,
    AccessibleCustomers,
    CustomerHierarchyStream,
    CampaignPerformance,
    CampaignHourlyPerformance,
    CampaignPerformanceByAgeRangeAndDevice,
    CampaignPerformanceByGenderAndDevice,
    CampaignPerformanceByLocation,
    GeotargetsStream,
    GeoPerformance,
]


class TapGoogleAds(Tap):
    """GoogleAds tap class."""

    name = "tap-googleads"

    # TODO: Add Descriptions
    config_jsonschema = th.PropertiesList(
        th.Property(
            "oauth_credentials.client_id",
            th.StringType,
        ),
        th.Property(
            "oauth_credentials.client_secret",
            th.StringType,
        ),
        th.Property(
            "developer_token",
            th.StringType,
        ),
        th.Property(
            "oauth_credentials.refresh_token",
            th.StringType,
        ),
        th.Property(
            "customer_id",
            th.StringType,
        ),
        th.Property(
            "performance_report_interval_days",
            th.IntegerType,
        )
    ).to_dict()

    def discover_streams(self) -> List[Stream]:
        """Return a list of discovered streams."""
        return [stream_class(tap=self) for stream_class in STREAM_TYPES]
