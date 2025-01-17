import logging

from checkov.cloudformation import cfn_utils
from checkov.cloudformation.cfn_utils import get_folder_definitions, create_file_abs_path
from checkov.cloudformation.checks.resource.registry import cfn_registry
from checkov.cloudformation.context_parser import ContextParser
from checkov.cloudformation.parser import parse
from checkov.cloudformation.parser.node import dict_node
from checkov.common.output.record import Record
from checkov.common.output.report import Report
from checkov.common.runners.base_runner import BaseRunner
from checkov.runner_filter import RunnerFilter


class Runner(BaseRunner):
    check_type = "cloudformation"

    def run(self, root_folder, external_checks_dir=None, files=None, runner_filter=RunnerFilter(), collect_skip_comments=True):
        report = Report(self.check_type)
        definitions = {}
        definitions_raw = {}
        if external_checks_dir:
            for directory in external_checks_dir:
                cfn_registry.load_external_checks(directory)

        if files:
            for file in files:
                (definitions[file], definitions_raw[file]) = parse(file)

        if root_folder:
            definitions, definitions_raw = get_folder_definitions(root_folder, runner_filter.excluded_paths)

        # Filter out empty files that have not been parsed successfully, and filter out non-CF template files
        definitions = {k: v for k, v in definitions.items() if v and isinstance(v, dict_node) and v.__contains__("Resources") and isinstance(v["Resources"], dict_node)}
        definitions_raw = {k: v for k, v in definitions_raw.items() if k in definitions.keys()}

        for cf_file in definitions.keys():

            file_abs_path = create_file_abs_path(root_folder, cf_file)

            if isinstance(definitions[cf_file], dict_node) and 'Resources' in definitions[cf_file].keys():
                cf_context_parser = ContextParser(cf_file, definitions[cf_file], definitions_raw[cf_file])
                logging.debug("Template Dump for {}: {}".format(cf_file, definitions[cf_file], indent=2))
                cf_context_parser.evaluate_default_refs()
                for resource_name, resource in definitions[cf_file]['Resources'].items():
                    resource_id = cf_context_parser.extract_cf_resource_id(resource, resource_name)
                    # check that the resource can be parsed as a CF resource
                    if resource_id:
                        entity_lines_range, entity_code_lines = cf_context_parser.extract_cf_resource_code_lines(resource)
                        if entity_lines_range and entity_code_lines:
                            # TODO - Variable Eval Message!
                            variable_evaluations = {}

                            skipped_checks = ContextParser.collect_skip_comments(entity_code_lines)
                            entity = {resource_name: resource}
                            results = cfn_registry.scan(cf_file, entity, skipped_checks,
                                                        runner_filter)
                            tags = cfn_utils.get_resource_tags(entity)
                            for check, check_result in results.items():
                                record = Record(check_id=check.id, check_name=check.name, check_result=check_result,
                                                code_block=entity_code_lines, file_path=cf_file,
                                                file_line_range=entity_lines_range, resource=resource_id,
                                                evaluations=variable_evaluations,check_class=check.__class__.__module__,
                                                file_abs_path=file_abs_path, entity_tags=tags)
                                report.add_record(record=record)
        return report

