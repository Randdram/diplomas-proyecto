-- Migración mínima para tu base MySQL (agrega la tabla 'diploma')
-- Ejecuta esto DESPUÉS de haber importado tu Dump20250915.sql

CREATE TABLE IF NOT EXISTS diploma (
  diploma_id BIGINT NOT NULL AUTO_INCREMENT,
  alumno_id BIGINT NOT NULL,
  curso_id INT NULL,
  folio CHAR(36) NOT NULL,
  ciclo VARCHAR(20) NOT NULL,
  fecha_emision DATE NOT NULL,
  hash_sha256 CHAR(64) NOT NULL,
  estado ENUM('VALIDO','ANULADO') NOT NULL DEFAULT 'VALIDO',
  pdf_path VARCHAR(255) NOT NULL,
  PRIMARY KEY (diploma_id),
  UNIQUE KEY uq_folio (folio),
  KEY idx_alumno (alumno_id),
  KEY idx_curso (curso_id),
  CONSTRAINT fk_diploma_alumno FOREIGN KEY (alumno_id) REFERENCES alumno(alumno_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_diploma_curso FOREIGN KEY (curso_id) REFERENCES curso(curso_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- Vista opcional para consultar diplomas con datos útiles
CREATE OR REPLACE VIEW vista_diplomas AS
SELECT
  d.diploma_id,
  d.folio,
  d.ciclo,
  d.fecha_emision,
  d.estado,
  d.hash_sha256,
  d.pdf_path,
  a.alumno_id,
  a.nombre AS alumno,
  a.curp,
  e.nombre AS escuela,
  g.nombre AS grado,
  c.nombre AS curso
FROM diploma d
JOIN alumno a ON a.alumno_id = d.alumno_id
LEFT JOIN inscripcion i ON i.alumno_id = a.alumno_id
LEFT JOIN curso c ON c.curso_id = COALESCE(d.curso_id, i.curso_id)
LEFT JOIN escuela e ON e.escuela_id = a.escuela_id
LEFT JOIN grado g ON g.grado_id = a.grado_id;
