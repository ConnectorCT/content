import demistomock as demisto
from CommonServerPython import *  # noqa # pylint: disable=unused-wildcard-import
from CommonServerUserPython import *  # noqa

import urllib3
from typing import Dict, Any, List, Tuple

# Disable insecure warnings
urllib3.disable_warnings()  # pylint: disable=no-member


''' CONSTANTS '''

ALL_SUPPORTED_EVENT_TYPES = ['alert', 'application', 'audit', 'network', 'page']
EVENT_TYPES_V1 = ['application', 'audit', 'network', 'page']  # api version - v1
EVENT_TYPES_V2 = ALL_SUPPORTED_EVENT_TYPES  # api version v2


''' CLIENT CLASS '''


class Client(BaseClient):
    """
    Client for Netskope RESTful API.

    Args:
        base_url (str): The base URL of Netskope.
        token (str): The token to authenticate against Netskope API.
        validate_certificate (bool): Specifies whether to verify the SSL certificate or not.
        proxy (bool): Specifies if to use XSOAR proxy settings.
    """

    def __init__(self, base_url: str, token: str, api_version: str, validate_certificate: bool, proxy: bool):
        super().__init__(base_url, verify=validate_certificate, proxy=proxy)
        if api_version == 'v1':
            self._session.params['token'] = token  # type: ignore
        else:
            self.headers = {'Netskope-Api-Token': token}

    def get_events_request_v1(self, event_type: str, last_run: dict, limit: Optional[int] = None) -> Dict:
        body = {
            'starttime': last_run.get(event_type),
            'endtime': int(datetime.now().timestamp()),
            'limit': limit,
            'type': event_type
        }
        response = self._http_request(method='GET', url_suffix='events', json_data=body)
        return response

    def get_alerts_request_v1(self, last_run: dict, limit: Optional[int] = None) -> list[Any] | Any:  # pragma: no cover
        """
        Get alerts generated by Netskope, including policy, DLP, and watch list alerts.

        Args:
            last_run (dict): Get alerts from certain time period.
            limit (Optional[int]): The maximum number of alerts to return (up to 10000).

        Returns:
            List[str, Any]: Netskope alerts.
        """

        url_suffix = 'alerts'
        body = {
            'starttime': last_run.get('alert'),
            'endtime': int(datetime.now().timestamp()),
            'limit': limit
        }
        response = self._http_request(method='GET', url_suffix=url_suffix, json_data=body)
        if response.get('status') == 'success':
            results = response.get('data', [])
            for event in results:
                populate_modeling_rule_fields(event, 'alert')
            return results
        return []

    def get_events_request_v2(self, event_type: str, last_run: dict, limit: Optional[int] = None) -> Dict:
        url_suffix = f'events/data/{event_type}'
        params = {'timeperiod': last_run.get(event_type), 'limit': limit}
        response = self._http_request(method='GET', url_suffix=url_suffix, headers=self.headers, params=params)
        return response


''' HELPER FUNCTIONS '''


def get_sorted_events_by_type(events: list, event_type: str = '') -> list:
    filtered_events = [event for event in events if event.get('source_log_event') == event_type]
    filtered_events.sort(key=lambda k: k.get('timestamp'))
    return filtered_events


def create_last_run(events: list, last_run: dict) -> dict:  # type: ignore
    """
    Args:
    events (list): list of the event from the api
    last_run (dict): the dictionary containing the last run times for the event types
    Returns:
    A dictionary with the times for the next run
    """
    for event_type in ALL_SUPPORTED_EVENT_TYPES:
        ordered_events_by_type = get_sorted_events_by_type(events, event_type)
        events_time = ordered_events_by_type[-1]['timestamp'] if ordered_events_by_type else last_run[event_type]
        last_run[event_type] = events_time
    return last_run


def populate_modeling_rule_fields(event: dict, event_type: str):
    event['source_log_event'] = event_type
    try:
        event['_time'] = timestamp_to_datestring(event['timestamp'] * 1000)
    except TypeError:
        # modeling rule will default on ingestion time if _time is missing
        pass


''' COMMAND FUNCTIONS '''


def test_module(client: Client, api_version: str, last_run: dict) -> str:

    fetch_events_command(client, api_version, last_run, max_fetch=1)
    return 'ok'


def get_events_v1(client: Client, last_run: dict, limit: Optional[int] = None) -> List[Any] | Any:  # pragma: no cover
    """
    Get all events extracted from Saas traffic and or logs.
    Args:
        client (Client): Netskope Client.
        last_run (dict): Get alerts from certain time period.
        limit (Optional[int]): The maximum number of alerts to return (up to 10000).
    Returns:
        events (list).
    """
    events = []
    for event_type in EVENT_TYPES_V1:
        response = client.get_events_request_v1(event_type, last_run, limit)
        if response.get('status') == 'success':
            results = response.get('data', [])
            for event in results:
                populate_modeling_rule_fields(event, event_type)
            events.extend(results)

    return events


def v1_get_events_command(client: Client, args: Dict[str, Any], last_run: dict) -> Tuple[CommandResults, list]:
    limit = arg_to_number(args.get('limit', 20))

    events = get_events_v1(client, last_run, limit)
    alerts = client.get_alerts_request_v1(last_run, limit)
    if alerts:
        events.extend(alerts)

    for event in events:
        event['timestamp'] = timestamp_to_datestring(event['timestamp'] * 1000)

    readable_output = tableToMarkdown('Events List:', events,
                                      removeNull=True,
                                      headers=['_id', 'timestamp', 'type', 'access_method', 'app', 'traffic_type'],
                                      headerTransform=string_to_table_header)

    results = CommandResults(outputs_prefix='Netskope.Event',
                             outputs_key_field='_id',
                             outputs=events,
                             readable_output=readable_output,
                             raw_response=events)
    return results, events


def get_events_v2(client, last_run: dict, limit: Optional[int] = None) -> List[Any] | Any:
    """
    Get all events extracted from Saas traffic and or logs.
    Args:
        client (Client): Netskope Client.
        last_run (dict): Get alerts from certain time period.
        limit (Optional[int]): The maximum number of alerts to return (up to 10000).
    Returns:
        events (list).
    """
    events = []
    for event_type in EVENT_TYPES_V2:
        response = client.get_events_request_v2(event_type, last_run, limit)
        if response.get('ok') == 1:
            results = response.get('result', [])
            for event in results:
                populate_modeling_rule_fields(event, event_type)
            events.extend(results)
    return events


def v2_get_events_command(client: Client, args: Dict[str, Any], last_run: dict) -> Tuple[CommandResults, list]:
    limit = arg_to_number(args.get('limit', 50))

    events = get_events_v2(client, last_run, limit)
    for event in events:
        event['timestamp'] = timestamp_to_datestring(event['timestamp'] * 1000)

    readable_output = tableToMarkdown('Events List:', events,
                                      removeNull=True,
                                      headers=['_id', 'timestamp', 'type', 'access_method', 'app', 'traffic_type'],
                                      headerTransform=string_to_table_header)

    results = CommandResults(outputs_prefix='Netskope.Event',
                             outputs_key_field='_id',
                             outputs=events,
                             readable_output=readable_output,
                             raw_response=events)

    return results, events


def fetch_events_command(client, api_version, last_run, max_fetch):
    if api_version == 'v1':
        events = get_events_v1(client, last_run, max_fetch)
        alerts = client.get_alerts_request_v1(last_run, max_fetch)
        if alerts:
            events.extend(alerts)
    else:
        events = get_events_v2(client, last_run, max_fetch)

    return events


''' MAIN FUNCTION '''


def main() -> None:  # pragma: no cover
    params = demisto.params()

    url = params.get('url')
    api_version = params.get('api_version')
    token = params.get('credentials', {}).get('password')
    base_url = urljoin(url, f'/api/{api_version}/')
    verify_certificate = not params.get('insecure', False)
    proxy = params.get('proxy', False)
    first_fetch = params.get('first_fetch')
    max_fetch = arg_to_number(params.get('max_fetch'))
    vendor, product = params.get('vendor', 'netskope'), params.get('product', 'netskope')

    demisto.debug(f'Command being called is {demisto.command()}')
    try:
        client = Client(base_url, token, api_version, verify_certificate, proxy)

        last_run = demisto.getLastRun()
        if not last_run:
            first_fetch = int(arg_to_datetime(first_fetch).timestamp())  # type: ignore[union-attr]
            last_run = {event_type: first_fetch for event_type in ALL_SUPPORTED_EVENT_TYPES}

        if demisto.command() == 'test-module':
            # This is the call made when pressing the integration Test button.
            result = test_module(client, api_version, last_run)
            return_results(result)

        elif demisto.command() == 'netskope-get-events':
            if api_version == 'v1':
                results, events = v1_get_events_command(client, demisto.args(), last_run)
            else:
                results, events = v2_get_events_command(client, demisto.args(), last_run)

            if argToBoolean(demisto.args().get('should_push_events', 'true')):
                send_events_to_xsiam(events=events, vendor=vendor, product=product)  # type: ignore
            return_results(results)

        elif demisto.command() == 'fetch-events':
            events = fetch_events_command(client, api_version, last_run, max_fetch)
            demisto.setLastRun(create_last_run(events, last_run))
            demisto.debug(f'Setting the last_run to: {last_run}')
            send_events_to_xsiam(events=events, vendor=vendor, product=product)

    # Log exceptions and return errors
    except Exception as e:
        return_error(f'Failed to execute {demisto.command()} command.\nError:\n{str(e)}')


''' ENTRY POINT '''


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()
