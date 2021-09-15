#!/usr/bin/python
import logging
import os
import requests
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from urllib.parse import quote
from datetime import datetime, timedelta
import veracross_api as v
import settings
import creds

# Setup logging
logFile = os.path.dirname(os.path.realpath(__file__)) + "/" + settings.logFile
logging.basicConfig(filename=logFile, level=logging.DEBUG)

# veracross-api setup
vc_info = {
    'school_short_name': 'da',
    'vcuser': creds.vcapiuser,
    'vcpass': creds.vcapipass
}
vc = v.Veracross(vc_info)

global vc_classes
global vc_students
global vc_enrollments
global vc_fac_staff


def log(log_data, level):
    print(log_data)
    if level == "info":
        logging.info(log_data)
    elif level == "error":
        logging.error(log_data)
    elif level == "debug":
        logging.debug(log_data)


def jss_validate_vc_class():
    global vc_classes

    # Create a list of all classes in VC
    classes = []
    for vcc in vc_classes:
        classes.append(vcc["class_id"])

    # Get all JAMF classes
    header = {"Accept": "application/json"}
    auth_phrase = (creds.jssuser, creds.jsspass)
    request_url = creds.jssserver + '/JSSResource/classes'

    jss_classes_response = requests.get(request_url, auth=auth_phrase, headers=header)
    if jss_classes_response.status_code == requests.codes.ok:
        jss_classes = jss_classes_response.json()
    else:
        log("Unable to get classes from JSS API")
        return

    for c in jss_classes.get("classes"):
        if c.get("name") not in classes:
            log("Deleting class {} from JAMF.".format(c.get("name")), "info")
            request_url = creds.jssserver + '/JSSResource/classes/id/' + str(c.get("id"))
            delete_response = requests.delete(request_url, auth=auth_phrase, headers=header)
            if delete_response.status_code == requests.codes.ok:
                log("Deleted class.", "info")
            else:
                log("Could not delete class", "info")


def jss_check_update_class(class_name, xml_data):
    """
    takes the xml data and posts it to JSS. checks to see if an object needs to be updated.
    """
    class_name = quote(class_name, safe='%2F')
    auth_phrase = (creds.jssuser, creds.jsspass)
    request_url = creds.jssserver + '/JSSResource/classes/name/' + class_name

    # Check for an existing class
    check_existing_class_response = requests.get(request_url,
                                                 auth=auth_phrase)

    if check_existing_class_response.status_code != requests.codes.ok:
        # response code is not 200
        # try to make a new class
        post_request_url = creds.jssserver + '/JSSResource/classes/id/-1'
        post_request = requests.post(url=post_request_url,
                                     auth=auth_phrase,
                                     verify=False,
                                     headers={'Content-Type': 'text/xml'},
                                     data=xml_data)

        if post_request.status_code != requests.codes.created:
            # response code is not 201
            log("ERROR: Failed to add class: {}. Response code: {}".format(class_name, str(
                post_request.status_code)),
                "error")
            return
        else:
            # response code is 201 - created
            new_class_id = ET.fromstring(post_request.text).find("id").text
            if int(new_class_id) >= 0:
                log("ADDED: Successfully added class " + class_name, "info")
                return
            else:
                log("ERROR: Failed to add class " + class_name, "error")
                return
    else:
        # response code is 200 - ok - an object exists
        jss_root = ET.fromstring(check_existing_class_response.text)
        jss_class_id = jss_root.find("id").text
        jss_class_name = jss_root.find("name").text
        jss_class_description = jss_root.find("description").text
        jss_students_list = sorted([item.text for item in jss_root.find("students").findall("student")])
        jss_teachers_list = sorted([item.text for item in jss_root.find("teachers").findall("teacher")])

        vc_root = ET.fromstring(xml_data)
        vc_class_name = vc_root.find("name").text
        vc_class_description = vc_root.find("description").text
        vc_students_list = sorted([item.text for item in vc_root.find("students").findall("student")])
        vc_teachers_list = sorted([item.text for item in vc_root.find("teachers").findall("teacher")])

        if int(jss_class_id) >= 0:
            # check the fields to see if they need updates
            def does_class_update():
                if jss_class_name != vc_class_name:
                    log("class name needs updating", "info")
                    return True
                elif jss_class_description != vc_class_description:
                    log("class description needs updating", "info")
                    return True
                elif jss_students_list != vc_students_list:
                    log("class students needs updating", "info")
                    log("existing class students: " + str(jss_students_list), "debug")
                    log("vc students: " + str(vc_students_list), "debug")
                    return True
                elif jss_teachers_list != vc_teachers_list:
                    log("class teachers needs updating", "info")
                    log("existing class teachers: " + str(jss_teachers_list), "debug")
                    log("vc teachers: " + str(vc_teachers_list), "debug")
                    return True
                else:
                    return False

            # update the existing class with info from VC if different than JSS data
            if does_class_update():
                log("some data changed, need to update", "info")
                update_request_url = creds.jssserver + '/JSSResource/classes/id/' + jss_class_id
                update_request = requests.put(url=update_request_url,
                                              auth=auth_phrase,
                                              verify=False,
                                              headers={'Content-Type': 'text/xml'},
                                              data=xml_data)

                if update_request.status_code != requests.codes.created:
                    # response code is not 201
                    log(
                        "ERROR: Failed to update class " + class_name + "response code: " +
                        requests.status_codes._codes[update_request.status_code], "error")
                    logging.debug(update_request.text)
                    return
                else:
                    # response code is 201 - created
                    update_class_id = ET.fromstring(update_request.text).find("id").text
                    if int(update_class_id) >= 0:
                        log("ADDED: Successfully updated class " +
                            class_name + " jss-id: " + update_class_id, "info")
                        return
                    else:
                        log("ERROR: Failed to update class " +
                            class_name + " jss-id < 0", "error")
                        return
            else:
                log("Skipped: Successfully skipped class, no update needed " +
                    jss_class_name + " jss-id: " +
                    jss_class_id, "info")
                return
        else:
            log("ERROR: Failed to update class " + class_name + " jss-id < 0", "debug")
            return


def format_vc_to_jss(classes):
    """
    takes the class data from Veracross and turns it into xml for JSS
    """
    global vc_fac_staff
    global vc_enrollments
    global vc_students

    for vcClass in classes:
        jss_post_teacher_username = ''
        jss_post_student_username = ''

        class_pk = str(vcClass.get("class_pk"))
        class_id = str(vcClass.get("class_id"))
        class_desc = str(vcClass.get("description"))
        class_school_level = str(vcClass.get("school_level"))
        class_course_type = str(vcClass.get("course_type"))

        log(
            f"Processing class id {class_pk} "
            f"Named: {class_id}, "
            f"Description: {class_desc}, "
            f"Level: {class_school_level}, "
            f"Type: {class_course_type}.",
            "info"
        )

        # optional filter to skip classes based on division
        if class_school_level in settings.skip_class_division_level:

            log(
                f"Skipping class because Division: {class_school_level}. "
                f"Type: {class_course_type}",
                "info"
            )
            continue

        # optional filter to skip classes based on course type
        elif class_course_type in settings.skip_class_type:
            log("Skipping class because class type: {}".format(class_course_type), "info")
            continue

        # escape the ampersands
        jss_post_class_name = escape(class_id)
        jss_post_class_description = escape(class_desc)

        # Create an xml string of teachers usernames
        teachers = vcClass.get("teachers")
        for teacher in teachers:
            if teacher.get("person_fk"):
                teacher_id = teacher.get("person_fk")
                for facstaff in vc_fac_staff:
                    facstaff_id = facstaff.get("person_pk")
                    if facstaff_id == teacher_id:
                        if facstaff.get("username"):
                            if facstaff.get("username"):
                                jss_post_teacher_username += '<teacher>' + facstaff.get(
                                    "username") + '</teacher>'

        # Create an xml string of students usernames
        for vcEnrollment in vc_enrollments:
            enrollment_class_id = str(vcEnrollment.get("class_fk"))
            if enrollment_class_id == class_pk:
                enrollment_id = vcEnrollment.get("student_fk")
                for vcStudent in vc_students:
                    person_pk = vcStudent.get("person_pk")
                    if person_pk == enrollment_id:
                        if vcStudent.get("username"):
                            jss_post_student_username += '<student>' + str(
                                vcStudent.get("username")) + '</student>'

        # Assemble xml into post-able data for JSS
        post_data = f'<?xml version="1.0" encoding="UTF-8"?>' \
            f'<class>' \
            f'<id>-1</id>' \
            f'<name>{jss_post_class_name}</name>' \
            f'<description>{jss_post_class_description}</description>' \
            f'<type>Usernames</type>' \
            f'<students>{jss_post_student_username}</students>' \
            f'<teachers>{jss_post_teacher_username}</teachers>' \
            f'</class>'
        jss_check_update_class(class_id, post_data)


def main():
    start_time = datetime.now()
    log("Starting sync at: " + str(start_time), "info")

    # Pull VC Data
    log("Getting Veracross Students.", "info")
    global vc_students
    vc_students = vc.pull('students')

    log("Getting Veracross Enrollments.", "info")
    global vc_enrollments
    vc_enrollments = vc.pull('enrollments')

    log("Getting Faculty & Staff.", "info")
    global vc_fac_staff
    vc_fac_staff = vc.pull('facstaff')

    log("Getting Classes.", "info")
    global vc_classes
    vc_classes = vc.pull('classes')

    """
    Sync classes from VC in JAMF
    """
    format_vc_to_jss(vc_classes)

    # set current time of update to the pickle file
    end_time = datetime.now()

    """
    Check for old classes in JAMF that should be removed
    """
    jss_validate_vc_class()

    log("Finishing at: " + str(end_time), "info")
    log("Time to complete script: " + str(end_time - start_time), "info")


# consider to be run directly or as a module.
if __name__ == '__main__':
    main()
