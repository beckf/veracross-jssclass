#!/usr/bin/python
import logging
import os
import pickle
import requests
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from urllib.parse import quote
from os.path import join, dirname
from datetime import datetime, timedelta
from dotenv import load_dotenv
import veracross_api as v
import settings

# Setup .env
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Store Vars in .env file.  see example.env file
jssuser = os.getenv("jssuser")
jsspass = os.getenv("jsspass")
jssserver = os.getenv("jssserver")
vcapiuser = os.getenv("vcapiuser")
vcapipass = os.getenv("vcapipass")
vcapiclient = os.getenv("vcapiclient")
logFile = "logVeracrossJSS.log"

# Setup logging
logFile = os.path.dirname(os.path.realpath(__file__)) + "/" + logFile
logging.basicConfig(filename=logFile, level=logging.DEBUG)

# Setup Pickle file
pickle_file = "importclass.pickle"

# Counters setup
errorCount = 0
skippedCount = 0
addedCount = 0
updatedCount = 0

# veracross-api setup
vc_info = {
    'school_short_name': vcapiclient,
    'vcuser': vcapiuser,
    'vcpass': vcapipass
}


def log(log_data, level):
    print(log_data)
    if level is "info":
        logging.info(log_data)
    elif level is "error":
        logging.error(log_data)
    elif level is "debug":
        logging.debug(log_data)


def jsspost(class_name, xml_data):
    """
    takes the xml data and posts it to JSS. checks to see if an object needs to be updated.
    """
    global errorCount
    global skippedCount
    global addedCount
    global updatedCount
    #
    class_name = quote(class_name, safe='%2F')
    auth_phrase = (jssuser, jsspass)
    request_url = jssserver + '/JSSResource/classes/name/' + class_name

    # Check for an existing class
    check_existing_class_response = requests.get(request_url,
                                                 auth=auth_phrase,
                                                 verify=False)

    if check_existing_class_response.status_code != requests.codes.ok:
        # response code is not 200
        # try to make a new class
        post_request_url = jssserver + '/JSSResource/classes/id/-1'
        post_request = requests.post(url=post_request_url,
                                     auth=auth_phrase,
                                     verify=False,
                                     headers={'Content-Type': 'text/xml'},
                                     data=xml_data)

        if post_request.status_code != requests.codes.created:
            # response code is not 201
            log("ERROR: Failed to add class: {}. Response code: {}".format(class_name, str(post_request.status_code)),
                "error")
            logging.debug(xml_data)
            logging.debug(post_request.text)
            errorCount += 1
            return
        else:
            # response code is 201 - created
            new_class_id = ET.fromstring(post_request.text).find("id").text
            if int(new_class_id) >= 0:
                log("ADDED: Successfully added class " + class_name, "info")
                addedCount += 1
                return
            else:
                log("ERROR: Failed to add class " + class_name, "error")
                errorCount += 1
                return
    else:
        # response code is 200 - ok - an object exists
        existing_root = ET.fromstring(check_existing_class_response.text)
        existing_class_id = existing_root.find("id").text
        existing_class_name = existing_root.find("name").text
        existing_class_description = existing_root.find("description").text
        existing_class_students = existing_root.find("students")
        existing_class_students_tostring = ET.tostring(existing_class_students, encoding="unicode")
        existing_class_teachers = existing_root.find("teachers")
        existing_class_teachers_tostring = ET.tostring(existing_class_teachers, encoding="unicode")

        vc_root = ET.fromstring(xml_data)
        vc_class_name = vc_root.find("name").text
        vc_class_description = vc_root.find("description").text
        vc_students = vc_root.find("students")
        vc_students_tostring = ET.tostring(vc_students, encoding="unicode")
        vc_teachers = vc_root.find("teachers")
        vc_teachers_tostring = ET.tostring(vc_teachers, encoding="unicode")

        if int(existing_class_id) >= 0:
            # check the fields to see if they need updates
            def does_class_update():
                if existing_class_name != vc_class_name:
                    log("class name needs updating", "info")
                    return True
                elif existing_class_description != vc_class_description:
                    log("class description needs updating", "info")
                    return True
                elif existing_class_students_tostring != vc_students_tostring:
                    log("class students needs updating", "info")
                    return True
                elif existing_class_teachers_tostring != vc_teachers_tostring:
                    log("class teachers needs updating", "info")
                    return True
                else:
                    log("class does not need updating", "info")
                    return False

            # update the existing class with info from VC
            if does_class_update():
                log("some data changed, need to update", "info")
                update_request_url = jssserver + '/JSSResource/classes/id/' + existing_class_id
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
                    errorCount += 1
                    return
                else:
                    # response code is 201 - created
                    update_class_id = ET.fromstring(update_request.text).find("id").text
                    if int(update_class_id) >= 0:
                        log("ADDED: Successfully updated class " + class_name + " id: " + update_class_id, "info")
                        updatedCount += 1
                        return
                    else:
                        log("ERROR: Failed to update class " + class_name + " class_id < 0", "error")
                        errorCount += 1
                        return
            else:
                log("Skipped: Successfully skipped class, no update needed " + existing_class_name + " id: " +
                    existing_class_id, "info")
                skippedCount += 1
                return
        else:
            log("ERROR: Failed to update class " + class_name + " class_id < 0", "debug")
            errorCount += 1
            return


def vcpull(resource):
    """
    retrieves data from the Veracross API using veracross_api package
    """
    param = {
        "updated_after": date_in_past,
    }
    vc = v.Veracross(vc_info)
    data = vc.pull(resource, parameters=param)
    return data


def vctoxml(vc_classes):
    """
    takes the class data from Veracross and turns it into xml for JSS

    """
    global skippedCount

    # Pull VC Data
    log("Getting Veracross Students.", "info")
    vcStudents = vcpull('students')

    log("Getting Veracross Enrollments.", "info")
    vcEnrollments = vcpull('enrollments')

    log("Getting Faculty & Staff.", "info")
    vcFacStaff = vcpull('facstaff')

    for vcClass in vc_classes:
        # jss_post_class_name = ''
        jss_post_teacher_username = ''
        jss_post_student_username = ''

        classpk = str(vcClass.get("class_pk"))
        classid = str(vcClass.get("class_id"))
        classdesc = str(vcClass.get("description"))
        classschool_level = str(vcClass.get("school_level"))
        classcourse_type = str(vcClass.get("course_type"))

        log(
            f"Processing class id {classpk} "
            f"Named: {classid}, "
            f"Description: {classdesc}, "
            f"Level: {classschool_level}, "
            f"Type: {classcourse_type}.",
            "info"
        )

        # optional filters to skip classes based on division and/or course type
        if classschool_level in settings.skip_class_division_level:
            skippedCount += 1
            log(
                f"Skipping class because Division: {classschool_level}. "
                f"Type: {classcourse_type}",
                "info"
            )
            continue
        elif classcourse_type in settings.skip_class_type:
            skippedCount += 1
            log("Skipping class because in {}".format(classcourse_type), "info")
            continue

        # escape the ampersands
        jss_post_class_name = escape(classid)
        jss_post_class_description = escape(classdesc)

        teachers = vcClass.get("teachers")
        for teacher in teachers:
            if teacher.get("person_fk"):
                teacherid = teacher.get("person_fk")
                for facstaff in vcFacStaff:
                    facstaff_id = facstaff.get("person_pk")
                    if facstaff_id == teacherid:
                        if facstaff.get("username"):
                            if facstaff.get("username"):
                                jss_post_teacher_username += '<teacher>' + facstaff.get(
                                    "username") + '</teacher>'

        for vcEnrollment in vcEnrollments:
            enrollment_class_id = str(vcEnrollment.get("class_fk"))
            if enrollment_class_id == classpk:
                enrollmentid = vcEnrollment.get("student_fk")
                for vcStudent in vcStudents:
                    personpk = vcStudent.get("person_pk")
                    if personpk == enrollmentid:
                        if vcStudent.get("username"):
                            jss_post_student_username += '<student>' + str(
                                vcStudent.get("username")) + '</student>'

        post_data = f'<?xml version="1.0" encoding="UTF-8"?>' \
            f'<class>' \
            f'<id>-1</id>' \
            f'<name>{jss_post_class_name}</name>' \
            f'<description>{jss_post_class_description}</description>' \
            f'<type>Usernames</type>' \
            f'<students>{jss_post_student_username}</students>' \
            f'<teachers>{jss_post_teacher_username}</teachers>' \
            f'</class>'
        jsspost(classid, post_data)


def get_classes():
    log("Getting Veracross Classes.", "info")
    vcclasses = vcpull('classes')
    return vcclasses


def make_xml(vcclasses):
    log("creating xml", "info")
    vctoxml(vcclasses)


def main():
    global date_in_past

    log("----- beginning of log -----","info")
    log(datetime.now(), "info")

    # Get date of last sync
    if os.path.isfile(pickle_file):
        previous_update_file = open(pickle_file, "rb")
        previous_update = pickle.load(previous_update_file)
        previous_update_file.close()

        # establish a date 3 days before the last update date
        threedays_before_last_update = previous_update.date() - timedelta(3)
        date_in_past = str(threedays_before_last_update)

        log("Previous update was on " + str(previous_update), "info")
        logging.info("Previous update was " + str(previous_update))
    else:
        # couldn't find a previous update so this is the 'updated_after' date
        date_in_past = "2019-06-24"

    data = get_classes()

    make_xml(data)

    log("Results: Imported " + str(addedCount) +
        " Updated " + str(updatedCount) +
        " Skipped " + str(skippedCount) +
        " Errors " + str( errorCount),
        "info")

    this_update_date = datetime.now()
    log("Current update finished " + str(this_update_date), "info")

    # set current time of update to the pickle file
    previous_update_file = open(pickle_file, "wb")
    pickle.dump(this_update_date, previous_update_file)
    previous_update_file.close()

    log("----- end of log -----", "info")


# consider to be run directly or as a module.
if __name__ == '__main__':
    main()
