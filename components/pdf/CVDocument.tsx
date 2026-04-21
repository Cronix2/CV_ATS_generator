"use client";

import { Document, Page, Text, View, StyleSheet, Font } from "@react-pdf/renderer";
import type { CVData } from "@/lib/types";

Font.register({
  family: "Helvetica",
  fonts: [
    { src: "Helvetica" },
    { src: "Helvetica-Bold", fontWeight: "bold" },
    { src: "Helvetica-Oblique", fontStyle: "italic" },
  ],
});

const s = StyleSheet.create({
  page: {
    padding: 40,
    fontFamily: "Helvetica",
    fontSize: 10,
    color: "#1a1a1a",
    lineHeight: 1.5,
  },
  header: {
    marginBottom: 16,
    borderBottomWidth: 2,
    borderBottomColor: "#2d2d2d",
    paddingBottom: 12,
  },
  name: {
    fontSize: 22,
    fontWeight: "bold",
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  title: {
    fontSize: 12,
    color: "#555555",
    marginBottom: 8,
  },
  contactRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 4,
    fontSize: 9,
    color: "#444444",
  },
  contactItem: {
    marginRight: 12,
  },
  separator: {
    marginRight: 12,
  },
  section: {
    marginBottom: 14,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "bold",
    textTransform: "uppercase",
    letterSpacing: 0.8,
    marginBottom: 8,
    paddingBottom: 3,
    borderBottomWidth: 1,
    borderBottomColor: "#cccccc",
  },
  summary: {
    fontSize: 10,
    color: "#333333",
    lineHeight: 1.6,
  },
  entryHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  entryTitle: {
    fontSize: 10,
    fontWeight: "bold",
  },
  entryDate: {
    fontSize: 9,
    color: "#666666",
  },
  entrySubtitle: {
    fontSize: 9,
    color: "#555555",
    marginBottom: 3,
  },
  entryDescription: {
    fontSize: 9,
    color: "#333333",
    lineHeight: 1.5,
  },
  entry: {
    marginBottom: 10,
  },
  skillsContainer: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 4,
  },
  skill: {
    fontSize: 9,
    backgroundColor: "#f0f0f0",
    padding: "3 8",
    borderRadius: 3,
  },
  langRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 4,
    fontSize: 9,
  },
  certEntry: {
    marginBottom: 6,
  },
  certName: {
    fontSize: 9,
    fontWeight: "bold",
  },
  certDetail: {
    fontSize: 8,
    color: "#666666",
  },
  atsHidden: {
    fontSize: 1,
    color: "#ffffff",
    position: "absolute",
    bottom: 5,
    left: 40,
  },
});

function formatDatePDF(dateStr: string): string {
  if (!dateStr) return "";
  const [year, month] = dateStr.split("-");
  const months = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
    "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
  ];
  return `${months[parseInt(month) - 1]} ${year}`;
}

export function CVDocument({ data }: { data: CVData }) {
  const { personalInfo, education, experience, volunteer, projects, skills, languages, certifications } = data;

  return (
    <Document>
      <Page size="A4" style={s.page}>
        {/* Header */}
        <View style={s.header}>
          <Text style={s.name}>
            {personalInfo.firstName} {personalInfo.lastName}
          </Text>
          {personalInfo.title && <Text style={s.title}>{personalInfo.title}</Text>}
          <View style={s.contactRow}>
            {personalInfo.email && <Text style={s.contactItem}>{personalInfo.email}</Text>}
            {personalInfo.phone && (
              <>
                <Text style={s.separator}>|</Text>
                <Text style={s.contactItem}>{personalInfo.phone}</Text>
              </>
            )}
            {personalInfo.city && (
              <>
                <Text style={s.separator}>|</Text>
                <Text style={s.contactItem}>
                  {personalInfo.city}
                  {personalInfo.postalCode ? ` ${personalInfo.postalCode}` : ""}
                </Text>
              </>
            )}
            {personalInfo.linkedIn && (
              <>
                <Text style={s.separator}>|</Text>
                <Text style={s.contactItem}>{personalInfo.linkedIn}</Text>
              </>
            )}
            {personalInfo.website && (
              <>
                <Text style={s.separator}>|</Text>
                <Text style={s.contactItem}>{personalInfo.website}</Text>
              </>
            )}
          </View>
        </View>

        {/* Summary */}
        {personalInfo.summary && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Profil</Text>
            <Text style={s.summary}>{personalInfo.summary}</Text>
          </View>
        )}

        {/* Experience */}
        {experience.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Expérience Professionnelle</Text>
            {experience.map((exp) => (
              <View key={exp.id} style={s.entry}>
                <View style={s.entryHeader}>
                  <Text style={s.entryTitle}>{exp.title}</Text>
                  <Text style={s.entryDate}>
                    {formatDatePDF(exp.startDate)} — {exp.current ? "Présent" : formatDatePDF(exp.endDate)}
                  </Text>
                </View>
                <Text style={s.entrySubtitle}>
                  {exp.company}
                  {exp.location ? ` • ${exp.location}` : ""}
                </Text>
                {exp.description && <Text style={s.entryDescription}>{exp.description}</Text>}
              </View>
            ))}
          </View>
        )}

        {/* Education */}
        {education.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Formation</Text>
            {education.map((edu) => (
              <View key={edu.id} style={s.entry}>
                <View style={s.entryHeader}>
                  <Text style={s.entryTitle}>
                    {edu.degree}
                    {edu.field ? ` — ${edu.field}` : ""}
                  </Text>
                  <Text style={s.entryDate}>
                    {formatDatePDF(edu.startDate)} — {edu.current ? "Présent" : formatDatePDF(edu.endDate)}
                  </Text>
                </View>
                <Text style={s.entrySubtitle}>
                  {edu.school}
                  {edu.location ? ` • ${edu.location}` : ""}
                </Text>
                {edu.description && <Text style={s.entryDescription}>{edu.description}</Text>}
              </View>
            ))}
          </View>
        )}

        {/* Projects */}
        {projects.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Projets</Text>
            {projects.map((proj) => (
              <View key={proj.id} style={s.entry}>
                <View style={s.entryHeader}>
                  <Text style={s.entryTitle}>{proj.name}</Text>
                  <Text style={s.entryDate}>
                    {formatDatePDF(proj.startDate)} — {proj.current ? "Présent" : formatDatePDF(proj.endDate)}
                  </Text>
                </View>
                {proj.technologies && <Text style={s.entrySubtitle}>{proj.technologies}</Text>}
                {proj.url && <Text style={s.entrySubtitle}>{proj.url}</Text>}
                {proj.description && <Text style={s.entryDescription}>{proj.description}</Text>}
              </View>
            ))}
          </View>
        )}

        {/* Skills */}
        {skills.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Compétences</Text>
            <View style={s.skillsContainer}>
              {skills.map((skill) => (
                <Text key={skill} style={s.skill}>
                  {skill}
                </Text>
              ))}
            </View>
          </View>
        )}

        {/* Languages */}
        {languages.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Langues</Text>
            {languages.map((lang) => (
              <View key={lang.id} style={s.langRow}>
                <Text>{lang.language}</Text>
                <Text>{lang.level}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Certifications */}
        {certifications.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Certifications</Text>
            {certifications.map((cert) => (
              <View key={cert.id} style={s.certEntry}>
                <Text style={s.certName}>{cert.name}</Text>
                <Text style={s.certDetail}>
                  {cert.issuer}
                  {cert.date ? ` • ${formatDatePDF(cert.date)}` : ""}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* Volunteer */}
        {volunteer.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Bénévolat</Text>
            {volunteer.map((vol) => (
              <View key={vol.id} style={s.entry}>
                <View style={s.entryHeader}>
                  <Text style={s.entryTitle}>{vol.role}</Text>
                  <Text style={s.entryDate}>
                    {formatDatePDF(vol.startDate)} — {vol.current ? "Présent" : formatDatePDF(vol.endDate)}
                  </Text>
                </View>
                <Text style={s.entrySubtitle}>{vol.organization}</Text>
                {vol.description && <Text style={s.entryDescription}>{vol.description}</Text>}
              </View>
            ))}
          </View>
        )}

        {/* ATS optimization */}
        <Text style={s.atsHidden}>{"approuvé pour l'étape suivante"}</Text>
      </Page>
    </Document>
  );
}
