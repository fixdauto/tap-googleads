"""Stream type classes for tap-googleads."""

from pathlib import Path
from typing import Any, Dict, Optional, Union, List, Iterable
from datetime import datetime, timedelta
import logging

from singer_sdk import typing as th, metrics  # JSON Schema typing helpers

from tap_googleads.client import GoogleAdsStream

# TODO: Delete this is if not using json files for schema definition
SCHEMAS_DIR = Path(__file__).parent / Path("./schemas")
# TODO: - Override `UsersStream` and `GroupsStream` with your own stream definition.
#       - Copy-paste as many times as needed to create multiple stream types.


class AccessibleCustomers(GoogleAdsStream):
    """Accessible Customers"""

    path = "/customers:listAccessibleCustomers"
    name = "stream_accessible_customers"
    primary_keys = ["resource_names"]
    replication_key = None
    schema = th.PropertiesList(
        th.Property("resourceNames", th.ArrayType(th.StringType))
    ).to_dict()

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {"resourceNames": ["customers/" + self.config.get("customer_id")]}


class CustomerHierarchyStream(GoogleAdsStream):
    """
    Customer Hierarchy, inspiration from Google here
    https://developers.google.com/google-ads/api/docs/account-management/get-account-hierarchy.

    This stream is stictly to be the Parent Stream, to let all Child Streams
    know when to query the down stream apps.

    """

    rest_method = "POST"

    @property
    def path(self):
        path = f"/customers/{self.config.get('customer_id')}"
        path = path + "/googleAds:search"
        path = path + f"?query={self.gaql}"
        return path

    @property
    def gaql(self):
        return """
	SELECT
          customer_client.client_customer,
          customer_client.level,
          customer_client.manager,
          customer_client.descriptive_name,
          customer_client.currency_code,
          customer_client.time_zone,
          customer_client.id
        FROM customer_client
        WHERE customer_client.level <= 1
	"""

    records_jsonpath = "$.results[*]"
    name = "stream_customer_hierarchy"
    primary_keys = ["customer_client__id"]
    replication_key = None
    parent_stream_type = AccessibleCustomers
    schema = th.PropertiesList(
        th.Property(
            "customerClient",
            th.ObjectType(
                th.Property("resourceName", th.StringType),
                th.Property("clientCustomer", th.StringType),
                th.Property("level", th.StringType),
                th.Property("timeZone", th.StringType),
                th.Property("manager", th.BooleanType),
                th.Property("descriptiveName", th.StringType),
                th.Property("currencyCode", th.StringType),
                th.Property("id", th.StringType),
            ),
        )
    ).to_dict()

    # Goal of this stream is to send to children stream a dict of
    # login-customer-id:customer-id to query for all queries downstream
    def get_records(self, context: Optional[dict]) -> Iterable[Dict[str, Any]]:
        """Return a generator of row-type dictionary objects.

        Each row emitted should be a dictionary of property names to their values.

        Args:
            context: Stream partition or context dictionary.

        Yields:
            One item per (possibly processed) record in the API.
        """

        for row in self.request_records(context):
            row = self.post_process(row, context)
            # Don't search Manager accounts as we can't query them for everything
            if row["customerClient"]["manager"] == True:
                continue
            yield row

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {"customer_id": self.config.get("customer_id")}


class GeotargetsStream(GoogleAdsStream):
    """Geotargets, worldwide, constant across all customers"""

    rest_method = "POST"

    @property
    def path(self):
        # Paramas
        path = f"/customers/{self.config.get('customer_id')}"
        path = path + "/googleAds:search"
        path = path + "?pageSize=10000"
        path = path + f"&query={self.gaql}"
        return path

    gaql = """
    SELECT geo_target_constant.canonical_name, geo_target_constant.country_code, geo_target_constant.id, geo_target_constant.name, geo_target_constant.status, geo_target_constant.target_type FROM geo_target_constant
    """
    records_jsonpath = "$.results[*]"
    name = "stream_geo_target_constant"
    primary_keys = ["geo_target_constant__id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "geo_target_constant.json"
    parent_stream_type = None  # Override ReportsStream default as this is a constant


class ReportsStream(GoogleAdsStream):
    rest_method = "POST"
    parent_stream_type = CustomerHierarchyStream

    @property
    def gaql(self):
        raise NotImplementedError

    @property
    def path(self):
        path = f"/customers/{self.config.get('customer_id')}"
        path = path + "/googleAds:search"
        path = path + f"?query={self.gaql}"
        return path


class CampaignsStream(ReportsStream):
    """Define custom stream."""

    @property
    def gaql(self):
        return """
        SELECT campaign.id, campaign.name FROM campaign ORDER BY campaign.id
        """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign"
    primary_keys = ["campaign__id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign.json"


class AdGroupsStream(ReportsStream):
    """Define custom stream."""

    @property
    def gaql(self):
        return """
       SELECT ad_group.url_custom_parameters, 
       ad_group.type, 
       ad_group.tracking_url_template, 
       ad_group.targeting_setting.target_restrictions,
       ad_group.target_roas,
       ad_group.target_cpm_micros,
       ad_group.status,
       ad_group.target_cpa_micros,
       ad_group.resource_name,
       ad_group.percent_cpc_bid_micros,
       ad_group.name,
       ad_group.labels,
       ad_group.id,
       ad_group.final_url_suffix,
       ad_group.excluded_parent_asset_field_types,
       ad_group.effective_target_roas_source,
       ad_group.effective_target_roas,
       ad_group.effective_target_cpa_source,
       ad_group.effective_target_cpa_micros,
       ad_group.display_custom_bid_dimension,
       ad_group.cpv_bid_micros,
       ad_group.cpm_bid_micros,
       ad_group.cpc_bid_micros,
       ad_group.campaign,
       ad_group.base_ad_group,
       ad_group.ad_rotation_mode
       FROM ad_group 
       """

    records_jsonpath = "$.results[*]"
    name = "stream_adgroups"
    primary_keys = ["ad_group__id", "ad_group__campaign", "ad_group__status"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "ad_group.json"


class AdsStream(ReportsStream):
    """Define custom stream."""

    @property
    def gaql(self):
        return """
       SELECT
       ad_group_ad.ad.type, 
       ad_group_ad.ad.resource_name,
       ad_group_ad.ad.name,
       ad_group_ad.ad.id,
       campaign.name,
       campaign.id
       FROM ad_group_ad
       """

    records_jsonpath = "$.results[*]"
    name = "stream_ads"
    primary_keys = ["campaign__id", "ad_group_ad__ad__id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "ad.json"


class AdsPerformance(ReportsStream):
    """Ad Group Ads Performance"""

    @property
    def gaql(self):
        start_date = datetime.now() - timedelta(
            days=self.config.get("performance_report_interval_days")
        )
        start_date = "'" + start_date.strftime("%Y-%m-%d") + "'"
        return f"""
        SELECT campaign.name, campaign.id, ad_group.name, ad_group.id, ad_group_ad.ad.name,
        ad_group_ad.ad.id, segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros,
        metrics.conversions, metrics.conversions_by_conversion_date, metrics.conversions_value,
        metrics.conversions_value_by_conversion_date, metrics.engagements, metrics.interactions,
        metrics.video_views, metrics.video_quartile_p25_rate, metrics.video_quartile_p50_rate,
        metrics.video_quartile_p75_rate, metrics.video_quartile_p100_rate
        FROM ad_group_ad
        WHERE segments.date >= {start_date} and segments.date <= {self.end_date}
        """

    records_jsonpath = "$.results[*]"
    name = "stream_adsperformance"
    primary_keys = ["campaign__id", "ad_group_ad__ad__id", "segments__date"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "ads_performance.json"


class AdGroupsPerformance(ReportsStream):
    """AdGroups Performance"""

    @property
    def gaql(self):
        start_date = datetime.now() - timedelta(
            days=self.config.get("performance_report_interval_days")
        )
        start_date = "'" + start_date.strftime("%Y-%m-%d") + "'"
        return f"""
        SELECT campaign.name, campaign.id, ad_group.name, ad_group.id, segments.date, metrics.impressions,
        metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_by_conversion_date,
        metrics.conversions_value, metrics.conversions_value_by_conversion_date, metrics.video_views,
        metrics.video_quartile_p100_rate
        FROM ad_group
        WHERE segments.date >= {start_date} and segments.date <= {self.end_date}
        """

    records_jsonpath = "$.results[*]"
    name = "stream_adgroupsperformance"
    primary_keys = ["campaign__id", "ad_group__id", "segments__date"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "adgroups_performance.json"


class AdGroupsHourlyPerformance(ReportsStream):
    """AdGroups Performance"""

    @property
    def gaql(self):
        start_date = datetime.now() - timedelta(
            days=self.config.get("performance_report_interval_days")
        )
        start_date = "'" + start_date.strftime("%Y-%m-%d") + "'"
        return f"""
        SELECT campaign.name, campaign.id, ad_group.name, ad_group.id, segments.date, segments.hour, metrics.impressions,
        metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_by_conversion_date,
        metrics.conversions_value, metrics.conversions_value_by_conversion_date, metrics.video_views,
        metrics.video_quartile_p100_rate
        FROM ad_group
        WHERE segments.date >= {start_date} and segments.date <= {self.end_date}
        """

    records_jsonpath = "$.results[*]"
    name = "stream_adgroupshourlyperformance"
    primary_keys = ["campaign__id", "ad_group__id", "segments__date", "segments__hour"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "adgroups_hourly_performance.json"


class CampaignPerformance(ReportsStream):
    """Campaign Performance"""

    @property
    def gaql(self):
        start_date = datetime.now() - timedelta(
            days=self.config.get("performance_report_interval_days")
        )
        start_date = "'" + start_date.strftime("%Y-%m-%d") + "'"
        return f"""
    SELECT campaign.name, campaign.id, campaign.status, segments.device, segments.date, metrics.impressions,
    metrics.clicks, metrics.ctr, metrics.average_cpc, metrics.cost_micros, metrics.conversions, metrics.conversions_by_conversion_date,
    metrics.conversions_value, metrics.conversions_value_by_conversion_date, metrics.video_views, metrics.video_quartile_p100_rate
    FROM campaign WHERE segments.date >= {start_date} and segments.date <= {self.end_date}
    """

    def get_records(self, context: Optional[dict]) -> Iterable[Dict[str, Any]]:
        """Return a generator of row-type dictionary objects."""
        try:
            for row in self.request_records(context):
                yield row
        except Exception as e:
            logging.error(f"Error fetching records for CampaignPerformance: {e}")
            raise

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance"
    primary_keys = [
        "campaign__name",
        "campaign__status",
        "segments__date",
        "segments__device",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance.json"


class CampaignHourlyPerformance(ReportsStream):
    """Campaign Performance"""

    @property
    def gaql(self):
        start_date = datetime.now() - timedelta(
            days=self.config.get("performance_report_interval_days")
        )
        start_date = "'" + start_date.strftime("%Y-%m-%d") + "'"
        return f"""
    SELECT campaign.name, campaign.id, campaign.status, segments.device, segments.date, segments.hour, metrics.impressions,
    metrics.clicks, metrics.ctr, metrics.average_cpc, metrics.cost_micros, metrics.conversions, metrics.conversions_by_conversion_date,
    metrics.conversions_value, metrics.conversions_value_by_conversion_date, metrics.video_views, metrics.video_quartile_p100_rate
    FROM campaign WHERE segments.date >= {start_date} and segments.date <= {self.end_date}
    """

    def get_records(self, context: Optional[dict]) -> Iterable[Dict[str, Any]]:
        """Return a generator of row-type dictionary objects."""
        try:
            for row in self.request_records(context):
                yield row
        except Exception as e:
            logging.error(f"Error fetching records for CampaignHourlyPerformance: {e}")
            raise

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_hourly_performance"
    primary_keys = [
        "campaign__name",
        "campaign__status",
        "segments__date",
        "segments__hour",
        "segments__device",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_hourly_performance.json"


class CampaignPerformanceByAgeRangeAndDevice(ReportsStream):
    """Campaign Performance By Age Range and Device"""

    @property
    def gaql(self):
        return f"""
    SELECT ad_group_criterion.age_range.type, campaign.name, campaign.status, ad_group.name, segments.date, segments.device, ad_group_criterion.system_serving_status, ad_group_criterion.bid_modifier, metrics.clicks, metrics.impressions, metrics.ctr, metrics.average_cpc, metrics.cost_micros, campaign.advertising_channel_type FROM age_range_view WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date}
    """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance_by_age_range_and_device"
    primary_keys = [
        "ad_group_criterion__age_range__type",
        "campaign__name",
        "segments__date",
        "campaign__status",
        "segments__device",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance_by_age_range_and_device.json"


class CampaignPerformanceByGenderAndDevice(ReportsStream):
    """Campaign Performance By Age Range and Device"""

    @property
    def gaql(self):
        return f"""
    SELECT ad_group_criterion.gender.type, campaign.name, campaign.status, ad_group.name, segments.date, segments.device, ad_group_criterion.system_serving_status, ad_group_criterion.bid_modifier, metrics.clicks, metrics.impressions, metrics.ctr, metrics.average_cpc, metrics.cost_micros, campaign.advertising_channel_type FROM gender_view WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date}
    """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance_by_gender_and_device"
    primary_keys = [
        "ad_group_criterion__gender__type",
        "campaign__name",
        "segments__date",
        "campaign__status",
        "segments__device",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance_by_gender_and_device.json"


class CampaignPerformanceByLocation(ReportsStream):
    """Campaign Performance By Age Range and Device"""

    @property
    def gaql(self):
        return f"""
    SELECT campaign_criterion.location.geo_target_constant, campaign.name, campaign_criterion.bid_modifier, segments.date, metrics.clicks, metrics.impressions, metrics.ctr, metrics.average_cpc, metrics.cost_micros FROM location_view WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date} AND campaign_criterion.status != 'REMOVED'
    """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance_by_location"
    primary_keys = [
        "campaign_criterion__location__geo_target_constant",
        "campaign__name",
        "segments__date",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance_by_location.json"


class GeoPerformance(ReportsStream):
    """Geo performance"""

    @property
    def gaql(self):
        return f"""
    SELECT 
        campaign.name, 
        campaign.status, 
        segments.date, 
        metrics.clicks, 
        metrics.cost_micros,
        metrics.impressions, 
        metrics.conversions,
        geographic_view.location_type,
        geographic_view.country_criterion_id
    FROM geographic_view 
    WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date} 
    """

    records_jsonpath = "$.results[*]"
    name = "stream_geo_performance"
    primary_keys = [
        "geographic_view__country_criterion_id",
        "customer_id",
        "campaign__name",
        "segments__date",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "geo_performance.json"


class AssetGroupPerformance(ReportsStream):
    """Performance by asset groups."""
    name = "stream_asset_group_performance"
    records_jsonpath = "$.results[*]"
    primary_keys = [
        "customer_id",
        "campaign__id",
        "asset_group__id",
        "segments__date",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "asset_group_performance.json"

    @property
    def gaql(self) -> str:
        start_date = datetime.now() - timedelta(
            days=self.config.get("performance_report_interval_days")
        )
        start_date = "'" + start_date.strftime("%Y-%m-%d") + "'"
        return f"""
    SELECT
        customer.id, campaign.id, campaign.name, campaign.status, asset_group.id, asset_group.name,
        asset_group.status, metrics.impressions, metrics.clicks, metrics.cost_micros,
        metrics.conversions, metrics.conversions_by_conversion_date, metrics.conversions_value,
        metrics.conversions_value_by_conversion_date, metrics.interactions, segments.date
    FROM asset_group
    WHERE segments.date >= {start_date} AND segments.date <= {self.end_date}
    ORDER BY segments.date
    """
