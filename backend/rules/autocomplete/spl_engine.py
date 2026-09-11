"""
SPL (Splunk Search Processing Language) autocomplete engine
"""

from typing import Dict, List, Optional, Tuple
from .base import AutocompleteEngine
from .suggestions import Suggestion, SuggestionKind


class SPLAutocompleteEngine(AutocompleteEngine):
    """
    Autocomplete for Splunk SPL detection rules.

    SPL Query Structure:
    index=<index> sourcetype=<sourcetype>
    | command1 args
    | command2 args
    ...
    """

    # Common Splunk search commands (pipe commands)
    SPL_COMMANDS = [
        'stats', 'eval', 'where', 'table', 'fields', 'rename', 'sort',
        'dedup', 'head', 'tail', 'rex', 'regex', 'search', 'lookup',
        'join', 'append', 'appendcols', 'appendpipe', 'transaction',
        'timechart', 'chart', 'top', 'rare', 'bucket', 'bin',
        'convert', 'fillnull', 'filldown', 'streamstats', 'eventstats',
        'inputlookup', 'outputlookup', 'tstats', 'mstats', 'datamodel',
        'makeresults', 'multikv', 'mvexpand', 'mvkv', 'outputtext',
        'transpose', 'untable', 'xyseries', 'fieldformat', 'format',
        'highlight', 'return', 'set', 'abstract', 'addcoltotals',
        'addinfo', 'addtotals', 'anomalies', 'anomalydetection',
        'anomalousvalue', 'associate', 'audit', 'autoregress', 'cluster',
        'cofilter', 'collect', 'concurrency', 'contingency', 'correlate',
        'dbinspect', 'diff', 'erex', 'extract', 'findtypes', 'folderize',
        'foreach', 'gauge', 'gentimes', 'geom', 'geomfilter', 'geostats',
        'history', 'iconify', 'kv', 'kvform', 'localop', 'map', 'metadata',
        'metasearch', 'meventcounttype', 'mvcombine', 'normalize', 'overlap',
        'pivot', 'predict', 'rangemap', 'redistribute', 'relevancy', 'reltime',
        'replace', 'require', 'rest', 'savedsearch', 'script', 'selfjoin',
        'sendalert', 'sendemail', 'setfields', 'sichart', 'sirare', 'sitimechart',
        'sistats', 'sitop', 'strcat', 'tags', 'tojson', 'trendline',
        'typeahead', 'typelearner', 'typer', 'union', 'uniq', 'walklex',
        'xmlkv', 'xmlunescape', 'xpath',
    ]

    # Common Splunk eval functions
    SPL_EVAL_FUNCTIONS = [
        'abs', 'acos', 'acosh', 'asin', 'asinh', 'atan', 'atanh', 'atan2',
        'ceiling', 'cidrmatch', 'coalesce', 'commands', 'cos', 'cosh',
        'exact', 'exp', 'floor', 'hypot', 'if', 'in', 'isbool', 'isint',
        'isnotnull', 'isnull', 'isnum', 'isstr', 'json_array',
        'json_array_to_mv', 'json_extract', 'json_extract_exact',
        'json_keys', 'json_object', 'json_set', 'json_set_exact',
        'json_valid', 'len', 'like', 'ln', 'log', 'lower', 'ltrim',
        'match', 'max', 'md5', 'min', 'mktime', 'mvappend', 'mvcount',
        'mvdedup', 'mvfilter', 'mvfind', 'mvindex', 'mvjoin', 'mvmap',
        'mvrange', 'mvsort', 'mvzip', 'now', 'null', 'nullif',
        'pi', 'pow', 'printf', 'random', 'relative_time', 'replace',
        'round', 'rtrim', 'searchmatch', 'sha1', 'sha256', 'sha512',
        'sigfig', 'sin', 'sinh', 'spath', 'split', 'sqrt', 'strftime',
        'strptime', 'substr', 'sum', 'tan', 'tanh', 'time', 'tonumber',
        'tostring', 'trim', 'typeof', 'upper', 'urldecode', 'validate',
    ]

    # Common Splunk stats functions
    SPL_STATS_FUNCTIONS = [
        'avg', 'count', 'dc', 'distinct_count', 'earliest', 'estdc',
        'estdc_error', 'exactperc', 'first', 'last', 'latest', 'list',
        'max', 'mean', 'median', 'min', 'mode', 'p50', 'p90', 'p95',
        'p99', 'perc', 'percentile', 'range', 'rate', 'sparkline',
        'stdev', 'stdevp', 'sum', 'sumsq', 'upperperc', 'values', 'var', 'varp',
    ]

    # Common Splunk indexes
    SPL_INDEXES = [
        'main', 'security', 'windows', 'linux', 'network', 'firewall',
        'endpoint', 'proxy', 'dns', 'auth', 'audit', 'syslog',
        'wineventlog', 'sysmon', 'o365', 'aws', 'azure', 'gcp',
    ]

    # Common Splunk sourcetypes
    SPL_SOURCETYPES = [
        'WinEventLog:Security', 'WinEventLog:System', 'WinEventLog:Application',
        'XmlWinEventLog:Security', 'XmlWinEventLog:Microsoft-Windows-Sysmon/Operational',
        'syslog', 'access_combined', 'linux_secure', 'linux_audit',
        'cisco:asa', 'paloalto:firewall', 'crowdstrike:events:sensor',
        'aws:cloudtrail', 'aws:cloudwatch', 'azure:monitor:activity',
        'o365:management:activity', 'gsuite:reports:activity',
    ]

    # Common Splunk time modifiers
    SPL_TIME_MODIFIERS = [
        'earliest=-1h', 'earliest=-24h', 'earliest=-7d', 'earliest=-30d',
        'latest=now', 'latest=+0s',
    ]

    def analyze_context(self, text: str, position: int) -> Dict:
        """Analyze SPL context at cursor position."""
        before_cursor = text[:position]
        lines_before = before_cursor.split('\n')
        current_line = lines_before[-1] if lines_before else ''
        stripped = current_line.lstrip()

        section = 'search'

        # Detect pipe command context
        if '|' in before_cursor:
            # Find the last pipe and what comes after it
            last_pipe_pos = before_cursor.rfind('|')
            after_pipe = before_cursor[last_pipe_pos + 1:].lstrip()
            first_word = after_pipe.split()[0].lower() if after_pipe.split() else ''

            if first_word in ('eval', 'where', 'search', 'rex'):
                section = 'expression'
            elif first_word == 'stats':
                section = 'stats'
            elif first_word:
                section = 'command_args'
            else:
                section = 'command'
        elif stripped.startswith('index='):
            section = 'index_value'
        elif stripped.startswith('sourcetype='):
            section = 'sourcetype_value'
        elif not stripped or stripped.startswith('#'):
            section = 'comment'

        return {
            'section': section,
            'current_line': current_line,
        }

    def get_suggestions(
        self,
        prefix: str,
        context: Dict,
        data_source_id: Optional[str] = None,
    ) -> List[Suggestion]:
        """Generate SPL suggestions based on context."""
        section = context.get('section', 'search')
        suggestions: List[Suggestion] = []

        if section == 'command':
            for cmd in self.SPL_COMMANDS:
                suggestions.append(
                    Suggestion(
                        label=cmd,
                        kind=SuggestionKind.KEYWORD,
                        insertText=cmd,
                        detail='SPL command',
                        documentation=f'Splunk SPL pipe command: {cmd}',
                    )
                )

        elif section == 'stats':
            for fn in self.SPL_STATS_FUNCTIONS:
                suggestions.append(
                    Suggestion(
                        label=fn,
                        kind=SuggestionKind.FUNCTION,
                        insertText=fn,
                        detail='stats function',
                    )
                )

        elif section == 'expression':
            for fn in self.SPL_EVAL_FUNCTIONS:
                suggestions.append(
                    Suggestion(
                        label=fn,
                        kind=SuggestionKind.FUNCTION,
                        insertText=f'{fn}()',
                        detail='eval function',
                    )
                )

        elif section == 'index_value':
            for idx in self.SPL_INDEXES:
                suggestions.append(
                    Suggestion(
                        label=idx,
                        kind=SuggestionKind.VALUE,
                        insertText=idx,
                        detail='Splunk index',
                    )
                )

        elif section == 'sourcetype_value':
            for st in self.SPL_SOURCETYPES:
                suggestions.append(
                    Suggestion(
                        label=st,
                        kind=SuggestionKind.VALUE,
                        insertText=st,
                        detail='Splunk sourcetype',
                    )
                )

        else:
            # General search context: offer commands and keywords
            for cmd in self.SPL_COMMANDS:
                suggestions.append(
                    Suggestion(
                        label=f'| {cmd}',
                        kind=SuggestionKind.KEYWORD,
                        insertText=f'| {cmd} ',
                        detail='SPL command',
                    )
                )
            for mod in self.SPL_TIME_MODIFIERS:
                suggestions.append(
                    Suggestion(
                        label=mod,
                        kind=SuggestionKind.SNIPPET,
                        insertText=mod,
                        detail='time modifier',
                    )
                )

        return suggestions

    def validate_syntax(self, text: str) -> Tuple[bool, Optional[str]]:
        """Basic SPL syntax validation."""
        stripped = text.strip()
        if not stripped:
            return False, "Empty SPL query"
        # Check that every pipe is followed by a command
        import re
        dangling = re.search(r'\|\s*$', stripped)
        if dangling:
            return False, "SPL query ends with a dangling pipe operator"
        return True, None

    def rank_suggestions(self, suggestions: List[Suggestion], prefix: str) -> List[Suggestion]:
        """Prioritize keywords (commands) > functions > values > others."""
        kind_weight = {
            SuggestionKind.KEYWORD: 0,
            SuggestionKind.FUNCTION: 1,
            SuggestionKind.VALUE: 2,
            SuggestionKind.SNIPPET: 3,
            SuggestionKind.OPERATOR: 4,
            SuggestionKind.FIELD: 5,
            SuggestionKind.TEXT: 6,
        }

        def score(s: Suggestion):
            return (kind_weight.get(s.kind, 10), s.label.lower())

        return sorted(suggestions, key=score)
